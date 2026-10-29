import base64
import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from software_factory.github import GitHub
from software_factory.planning import main


@pytest.fixture
def boundary(tmp_path: Path) -> tuple[Path, dict, dict]:
    plan = {
        "version": 1,
        "repository": "Example/target",
        "spec_id": "checkout",
        "source": {"path": "SPEC.md", "commit": "a" * 40},
        "stories": [
            {
                "id": "US-02",
                "title": "Order",
                "scope": "Place order.",
                "acceptance_criteria": ["Order exists."],
                "verification": ["Run tests."],
                "depends_on": ["US-01"],
            },
            {
                "id": "US-01",
                "title": "View",
                "scope": "View checkout.",
                "acceptance_criteria": ["Total exists."],
                "verification": ["Run tests."],
                "depends_on": [],
            },
        ],
    }
    spec = "Spec ID: `checkout`\n### US-01: View\nDepends on: None.\n### US-02: Order\nDepends on: US-01.\n"
    state = {"issues": [], "labels": [], "calls": [], "spec": base64.b64encode(spec.encode()).decode(), "sha": "a" * 40}
    (tmp_path / "plan.json").write_text(json.dumps(plan))
    (tmp_path / "state.json").write_text(json.dumps(state))
    gh = tmp_path / "gh"
    gh.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
p = Path(os.environ["FAKE_STATE"])
s = json.loads(p.read_text())
a = sys.argv[1:]
endpoint = a[3].replace("repos/example/TARGET", "repos/Example/target")
method = a[a.index("--method") + 1]
payload = json.load(sys.stdin) if "--input" in a else None
s["calls"].append([method, endpoint, payload])
response = None
if endpoint == "user": response = {"login": s.get("login", "operator")}
elif endpoint == "repos/Example/target": response = {"full_name": s.get("repository", "Example/target")}
elif endpoint.startswith("repos/Example/target/commits/"):
    response = {"sha": s["sha"], "commit": {"tree": {"sha": "c" * 40}}}
elif endpoint.startswith("repos/Example/target/git/trees/"):
    response = {"tree": [{"path": s.get("source_path", "SPEC.md"), "type": "blob",
                           "mode": s.get("mode", "100644"), "sha": "d" * 40}]}
elif endpoint.startswith("repos/Example/target/contents/"):
    response = {"type": "file", "encoding": "base64", "content": s["spec"]}
elif endpoint.startswith("repos/Example/target/issues?"): response = [s["issues"]]
elif endpoint.endswith("/labels") and "/issues/" in endpoint and method == "POST":
    n = int(endpoint.split("/issues/")[1].split("/")[0])
    issue = next(i for i in s["issues"] if i["number"] == n)
    if not any(x["name"] == "agent:implement" for x in issue["labels"]):
        issue["labels"].append({"name": "agent:implement"})
    response = issue["labels"]
    if s.get("activation_failure") == n:
        p.write_text(json.dumps(s)); sys.exit(1)
    if s.get("activation_invalid") == n: response = []
    if s.get("activation_bad_label") == n: response = [{"name": None}]
    if s.get("activation_dropped_labels") == n: response = [{"name": "agent:implement"}]
elif endpoint.startswith("repos/Example/target/labels?"): response = [s["labels"]]
elif endpoint == "repos/Example/target/labels" and method == "POST":
    s["labels"].append({"name": payload["name"]}); response = s["labels"][-1]
    if s.get("label_failure"):
        p.write_text(json.dumps(s)); sys.exit(1)
elif endpoint == "repos/Example/target/issues" and method == "POST":
    n = len(s["issues"]) + 1
    issue = {**payload, "number": n, "html_url": f"https://github.com/Example/target/issues/{n}",
             "labels": [{"name": x} for x in payload["labels"]]}
    if s.get("uncertain_absent"):
        p.write_text(json.dumps(s)); sys.exit(1)
    s["issues"].append(issue); response = issue
    if s.get("invalid_response"): response = {**issue, "title": "incorrect"}
    if s.get("uncertain") or (s.get("uncertain_second") and n == 2):
        p.write_text(json.dumps(s)); sys.exit(1)
else: sys.exit(2)
p.write_text(json.dumps(s))
print(json.dumps(response))
""")
    gh.chmod(0o755)
    return tmp_path, plan, state


def invoke(path: Path, *args: str, command: str = "publish") -> subprocess.CompletedProcess:
    env = {**os.environ, "PATH": f"{path}{os.pathsep}{os.environ['PATH']}", "FAKE_STATE": str(path / "state.json")}
    argv = ["planning", command, "--plan", str(path / "plan.json"), *args]
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        patch.dict(os.environ, env),
        patch.object(sys, "argv", argv),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        code = main()
    return subprocess.CompletedProcess(argv, code, stdout.getvalue(), stderr.getvalue())


def state(path: Path) -> dict:
    return json.loads((path / "state.json").read_text())


def test_activation_queues_entire_backlog_and_runner_still_blocks_dependencies(
    boundary: tuple[Path, dict, dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import Mock

    from software_factory.config import Config
    from software_factory.runner import AgentRuntime, Runner

    path, _, _ = boundary
    assert invoke(path).returncode == 0
    env = {**os.environ, "PATH": f"{path}{os.pathsep}{os.environ['PATH']}", "FAKE_STATE": str(path / "state.json")}
    command = [sys.executable, "-m", "software_factory.planning", "activate", "--plan", str(path / "plan.json")]
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    assert "US-01: queued #1" in result.stdout and "US-02: queued #2" in result.stdout
    issues = state(path)["issues"]
    assert all(any(label["name"] == "agent:implement" for label in i["labels"]) for i in issues)
    again = subprocess.run(command, capture_output=True, text=True, env=env)
    assert again.returncode == 0 and "already queued" in again.stdout
    gh = GitHub("Example/target", Mock())
    gh.api = lambda *args, **kwargs: [issues]
    gh.default_branch = Mock(return_value="main")
    gh.closing_prs = Mock(return_value=[])
    gh.discover = lambda: [i["number"] for i in issues if any(x["name"] == "agent:implement" for x in i["labels"])]
    gh.issue_for_eligibility = lambda number: next(i.copy() for i in issues if i["number"] == number)
    gh.open_pr = Mock(return_value="https://github.com/Example/target/pull/9")
    gh.comment = Mock()
    claims = []

    def claim(number: int) -> None:
        claims.append(number)
        issue = next(i for i in issues if i["number"] == number)
        issue["labels"] = [label for label in issue["labels"] if label["name"] != "agent:implement"]

    gh.remove_trigger = claim
    monkeypatch.setattr("software_factory.runner.GitHub", lambda *args: gh)
    runner = Runner(Config("Example/target", "model", "image", path), AgentRuntime("image", "unix:///socket"))
    runner.poll_once()
    assert claims == [1]
    assert any(label["name"] == "agent:implement" for label in issues[1]["labels"])
    gh.closing_prs.return_value = [
        {"merged": True, "baseRefName": "main", "baseRepository": {"nameWithOwner": "Example/target"}}
    ]
    runner.poll_once()
    assert claims == [1, 2]


@pytest.mark.parametrize("damage", ["login", "repository", "missing", "duplicate", "same-number", "malformed", "draft"])
def test_activation_preflight_blocks_writes(boundary: tuple[Path, dict, dict], damage: str) -> None:
    path, plan, _ = boundary
    assert invoke(path).returncode == 0
    s = state(path)
    if damage == "login":
        s["login"] = ""
    elif damage == "repository":
        s["repository"] = "other/repo"
    elif damage == "missing":
        s["issues"].pop()
    elif damage == "duplicate":
        s["issues"].append({**s["issues"][0], "number": 9, "html_url": "https://github.com/Example/target/issues/9"})
    elif damage == "same-number":
        s["issues"][1].update(number=1, html_url="https://github.com/Example/target/issues/1")
    elif damage == "malformed":
        s["issues"][1]["body"] = "private invalid content"
    else:
        plan["source"]["commit"] = None
        (path / "plan.json").write_text(json.dumps(plan))
    before = len(s["calls"])
    (path / "state.json").write_text(json.dumps(s))
    result = invoke(path, command="activate")
    assert result.returncode == 1
    assert all(c[0] == "GET" for c in state(path)["calls"][before:])


@pytest.mark.parametrize(
    "failure", ["activation_failure", "activation_invalid", "activation_bad_label", "activation_dropped_labels"]
)
def test_activation_stops_on_unconfirmed_label_write(boundary: tuple[Path, dict, dict], failure: str) -> None:
    path, _, _ = boundary
    assert invoke(path).returncode == 0
    s = state(path)
    s[failure] = 2
    (path / "state.json").write_text(json.dumps(s))
    result = invoke(path, command="activate")
    assert result.returncode == 1
    assert "US-01: queued #1" in result.stdout
    assert "US-02" in result.stderr and "uncertain" in result.stderr
    assert sum(c[0] == "POST" and "/issues/2/labels" in c[1] for c in state(path)["calls"]) == 1


def test_activation_uses_current_edits_and_orders_by_issue_number(boundary: tuple[Path, dict, dict]) -> None:
    path, _, _ = boundary
    assert invoke(path).returncode == 0
    s = state(path)
    first, second = s["issues"]
    first.update(number=8, html_url="https://github.com/Example/target/issues/8")
    second.update(number=3, html_url="https://github.com/Example/target/issues/3", title="Edited title")
    second["body"] = second["body"].replace('"depends_on": ["US-01"]', '"depends_on": []') + "Edited task\n"
    second["labels"].append({"name": "operator-label"})
    (path / "state.json").write_text(json.dumps(s))
    before = len(s["calls"])
    result = invoke(path, command="activate")
    assert result.returncode == 0, result.stderr
    assert result.stdout.index("US-02: queued #3") < result.stdout.index("US-01: queued #8")
    writes = [call for call in state(path)["calls"][before:] if call[0] == "POST"]
    assert [call[1] for call in writes] == [
        "repos/Example/target/issues/3/labels",
        "repos/Example/target/issues/8/labels",
    ]
    assert all(call[2] == {"labels": ["agent:implement"]} for call in writes)
    assert {label["name"] for label in state(path)["issues"][1]["labels"]} == {
        "factory:generated",
        "operator-label",
        "agent:implement",
    }
    before = len(state(path)["calls"])
    again = invoke(path, command="activate")
    assert again.returncode == 0 and again.stdout.count("already queued") == 2
    assert all(call[0] == "GET" for call in state(path)["calls"][before:])


def test_activation_interruption_reports_uncertain_write(
    boundary: tuple[Path, dict, dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _, _ = boundary
    assert invoke(path).returncode == 0
    original = GitHub.api

    def interrupted(self: GitHub, endpoint: str, **kwargs: object) -> object:
        if endpoint == "issues/1/labels" and kwargs.get("method") == "POST":
            raise KeyboardInterrupt
        return original(self, endpoint, **kwargs)

    monkeypatch.setattr(GitHub, "api", interrupted)
    result = invoke(path, command="activate")
    assert result.returncode == 130
    assert "US-01" in result.stderr and "uncertain" in result.stderr
    assert not any(c[0] == "POST" and "/issues/" in c[1] for c in state(path)["calls"])


def test_preview_then_create_and_reconcile(boundary: tuple[Path, dict, dict]) -> None:
    path, plan, _ = boundary
    preview = invoke(path, "--dry-run")
    assert preview.returncode == 0, preview.stderr
    assert "[checkout/US-01] View" in preview.stdout
    assert "factory:generated" in preview.stdout
    assert all(call[0] == "GET" for call in state(path)["calls"])
    result = invoke(path)
    assert result.returncode == 0, result.stderr
    issues = state(path)["issues"]
    assert [i["title"] for i in issues] == ["[checkout/US-01] View", "[checkout/US-02] Order"]
    assert all(i["body"] in preview.stdout for i in issues)
    assert "agent:implement" not in result.stdout
    assert "created" in result.stdout
    again = invoke(path)
    assert again.returncode == 0, again.stderr
    assert "existing" in again.stdout
    assert len(state(path)["issues"]) == 2
    s = state(path)
    body = s["issues"][0]["body"]
    prefix, encoded = body.split("<!-- software-factory:planning\n")
    metadata = json.loads(encoded.split("\n")[0])
    s["issues"][0]["body"] = (
        prefix + "<!-- software-factory:planning\n" + json.dumps(dict(reversed(list(metadata.items())))) + "\n-->\n"
    )
    (path / "state.json").write_text(json.dumps(s))
    assert invoke(path).returncode == 0
    plan["source"]["commit"] = "b" * 40
    (path / "plan.json").write_text(json.dumps(plan))
    s = state(path)
    s["sha"] = "b" * 40
    (path / "state.json").write_text(json.dumps(s))
    assert invoke(path).returncode == 0
    assert len(state(path)["issues"]) == 2


def test_cli_subprocess_publication(boundary: tuple[Path, dict, dict]) -> None:
    path, _, _ = boundary
    env = {**os.environ, "PATH": f"{path}{os.pathsep}{os.environ['PATH']}", "FAKE_STATE": str(path / "state.json")}
    command = [sys.executable, "-m", "software_factory.planning", "publish", "--plan", str(path / "plan.json")]
    preview = subprocess.run(command + ["--dry-run"], capture_output=True, text=True, env=env)
    result = subprocess.run(command, capture_output=True, text=True, env=env)
    assert preview.returncode == result.returncode == 0
    assert all(issue["body"] in preview.stdout for issue in state(path)["issues"])
    assert "created" in result.stdout


@pytest.mark.parametrize(
    "setting", ["login", "repository", "sha", "label_failure", "uncertain_absent", "uncertain_second"]
)
def test_remote_failures_stop_without_blind_retries(boundary: tuple[Path, dict, dict], setting: str) -> None:
    path, _, s = boundary
    s[setting] = {"login": "", "repository": "other/repo", "sha": "b" * 40}.get(setting, True)
    (path / "state.json").write_text(json.dumps(s))
    result = invoke(path)
    assert result.returncode == 1
    calls = state(path)["calls"]
    creates = [c for c in calls if c[0] == "POST" and c[1].endswith("/issues")]
    if setting in {"login", "repository", "sha", "label_failure"}:
        assert not creates
    elif setting == "uncertain_absent":
        assert len(creates) == 1
        assert "inspection" in result.stderr.lower()
        assert "reconciled" not in result.stdout
    else:
        assert len(creates) == 2
        assert "created #1" in result.stdout
        assert "reconciled #2" in result.stdout
        assert "inspection" in result.stderr.lower()


def test_interrupted_create_requires_inspection(
    boundary: tuple[Path, dict, dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _, _ = boundary
    original = GitHub.api

    def interrupted(self: GitHub, endpoint: str, **kwargs: object) -> object:
        if endpoint == "issues" and kwargs.get("method") == "POST":
            raise KeyboardInterrupt
        return original(self, endpoint, **kwargs)

    monkeypatch.setattr(GitHub, "api", interrupted)
    result = invoke(path)
    assert result.returncode == 130
    assert "uncertain" in result.stderr
    assert not state(path)["issues"]


def test_invalid_create_response_is_reconciled_without_retry(boundary: tuple[Path, dict, dict]) -> None:
    path, _, s = boundary
    s["invalid_response"] = True
    (path / "state.json").write_text(json.dumps(s))
    result = invoke(path)
    assert result.returncode == 1
    assert "reconciled #1" in result.stdout
    assert "inspection" in result.stderr
    assert len(state(path)["issues"]) == 1


def test_republication_ignores_repository_identity_case(boundary: tuple[Path, dict, dict]) -> None:
    path, plan, s = boundary
    assert invoke(path).returncode == 0
    plan["repository"] = "example/TARGET"
    (path / "plan.json").write_text(json.dumps(plan))
    s = state(path)
    s["repository"] = "example/TARGET"
    (path / "state.json").write_text(json.dumps(s))
    assert invoke(path).returncode == 0
    assert len(state(path)["issues"]) == 2


def test_conflict_blocks_all_new_writes(boundary: tuple[Path, dict, dict]) -> None:
    path, plan, _ = boundary
    assert invoke(path).returncode == 0
    plan["stories"][0]["scope"] = "Changed."
    (path / "plan.json").write_text(json.dumps(plan))
    before = len(state(path)["calls"])
    result = invoke(path)
    assert result.returncode == 1
    assert "conflict" in result.stderr.lower()
    assert all(c[0] == "GET" for c in state(path)["calls"][before:])


def test_uncertain_create_stops_and_reconciles_without_retry(boundary: tuple[Path, dict, dict]) -> None:
    path, _, s = boundary
    s["uncertain"] = True
    (path / "state.json").write_text(json.dumps(s))
    result = invoke(path)
    assert result.returncode == 1
    assert "inspection" in result.stderr.lower()
    assert len(state(path)["issues"]) == 1
    assert sum(c[0] == "POST" and c[1].endswith("/issues") for c in state(path)["calls"]) == 1


@pytest.mark.parametrize("damage", ["duplicate", "malformed", "missing-metadata", "wrong-url"])
def test_bad_existing_generated_issues_block_writes(boundary: tuple[Path, dict, dict], damage: str) -> None:
    path, _, _ = boundary
    assert invoke(path).returncode == 0
    s = state(path)
    issue = s["issues"][0]
    if damage == "duplicate":
        s["issues"].append({**issue, "number": 99, "html_url": "https://github.com/Example/target/issues/99"})
    elif damage == "malformed":
        issue["body"] += "<!-- software-factory:planning"
    elif damage == "missing-metadata":
        issue["body"] = "ordinary text"
    else:
        issue["html_url"] = "https://github.com/other/repo/issues/1"
    (path / "state.json").write_text(json.dumps(s))
    before = len(s["calls"])
    result = invoke(path)
    assert result.returncode == 1
    assert all(c[0] == "GET" for c in state(path)["calls"][before:])


def test_publication_in_process_covers_real_cli(
    boundary: tuple[Path, dict, dict], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    path, _, _ = boundary
    monkeypatch.setenv("PATH", f"{path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_STATE", str(path / "state.json"))
    monkeypatch.setattr(sys, "argv", ["planning", "publish", "--plan", str(path / "plan.json")])
    assert main() == 0
    assert "created" in capsys.readouterr().out
    assert main() == 0
    assert "existing" in capsys.readouterr().out


def test_draft_plan_cannot_be_published(boundary: tuple[Path, dict, dict]) -> None:
    path, plan, _ = boundary
    plan["source"]["commit"] = None
    (path / "plan.json").write_text(json.dumps(plan))
    assert invoke(path, "--dry-run").returncode == 1
    assert all(c[0] == "GET" for c in state(path)["calls"])


def test_symlink_source_blocks_writes(boundary: tuple[Path, dict, dict]) -> None:
    path, _, s = boundary
    s["mode"] = "120000"
    (path / "state.json").write_text(json.dumps(s))
    assert invoke(path).returncode == 1
    assert all(c[0] == "GET" for c in state(path)["calls"])


def test_reserved_opener_in_source_path_never_creates_invalid_issue(boundary: tuple[Path, dict, dict]) -> None:
    path, plan, s = boundary
    plan["source"]["path"] = "<!-- software-factory:planning"
    s["source_path"] = plan["source"]["path"]
    (path / "plan.json").write_text(json.dumps(plan))
    (path / "state.json").write_text(json.dumps(s))
    assert invoke(path).returncode == 1
    assert all(c[0] == "GET" for c in state(path)["calls"])


def test_source_dependency_order_does_not_change_graph(boundary: tuple[Path, dict, dict]) -> None:
    path, plan, s = boundary
    third = {**plan["stories"][1], "id": "US-03", "title": "Third"}
    plan["stories"].append(third)
    plan["stories"][0]["depends_on"] = ["US-03", "US-01"]
    spec = (
        "Spec ID: `checkout`\n### US-01: View\nDepends on: None.\n"
        "### US-02: Order\nDepends on: US-01, US-03.\n### US-03: Third\nDepends on: None.\n"
    )
    s["spec"] = base64.b64encode(spec.encode()).decode()
    (path / "plan.json").write_text(json.dumps(plan))
    (path / "state.json").write_text(json.dumps(s))
    assert invoke(path, "--dry-run").returncode == 0


def test_bad_provenance_blocks_writes(boundary: tuple[Path, dict, dict]) -> None:
    path, _, s = boundary
    s["spec"] = base64.b64encode(b"Spec ID: `other`\n").decode()
    (path / "state.json").write_text(json.dumps(s))
    result = invoke(path)
    assert result.returncode == 1
    assert all(c[0] == "GET" for c in state(path)["calls"])
