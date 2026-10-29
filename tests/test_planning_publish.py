import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from software_factory.planning import validate_plan
from software_factory.planning.activate import activate
from software_factory.planning.publish import existing, metadata, publish, render
from software_factory.process import FactoryError


@pytest.fixture
def plan() -> dict:
    return {
        "version": 1,
        "repository": "Example/target",
        "spec_id": "checkout",
        "source": {"path": "SPEC.md", "commit": "a" * 40},
        "stories": [
            {
                "id": "US-01",
                "title": "View",
                "scope": "View checkout.",
                "acceptance_criteria": ["Total exists."],
                "verification": ["Run tests."],
                "depends_on": [],
            },
            {
                "id": "US-02",
                "title": "Order",
                "scope": "Place order.",
                "acceptance_criteria": ["Order exists."],
                "verification": ["Run tests."],
                "depends_on": ["US-01"],
            },
        ],
    }


def test_existing_inspects_only_open_issues_and_rejects_duplicates(plan: dict) -> None:
    title, body = render(plan, plan["stories"][0])
    issue = {
        "number": 1,
        "html_url": "https://github.com/Example/target/issues/1",
        "title": title,
        "body": body,
        "labels": [{"name": "factory:generated"}],
    }
    gh = Mock()
    gh.api.return_value = [[issue]]
    gh.items.side_effect = lambda value, **kwargs: value[0]
    assert existing(gh, plan) == {"checkout/US-01": issue}
    gh.api.assert_called_once_with("issues?state=open&per_page=100", pages=True)
    gh.api.return_value = [[issue, {**issue, "number": 2, "html_url": "https://github.com/Example/target/issues/2"}]]
    with pytest.raises(FactoryError, match="Duplicate"):
        existing(gh, plan)


def test_publish_and_activate_in_process(
    plan: dict, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    class Boundary:
        def __init__(self) -> None:
            self.issues = []
            self.labels = []
            self.commands = self

        def run(self, *args: object, **kwargs: object) -> str:
            return json.dumps({"login": "operator"})

        def items(self, value: object, **kwargs: object) -> list:
            return value[0] if kwargs.get("pages") else value

        def api(self, path: str, *, payload: dict | None = None, method: str = "GET", **kwargs: object) -> object:
            if path == "":
                return {"full_name": "Example/target"}
            if path.startswith("commits/"):
                return {"sha": "a" * 40, "commit": {"tree": {"sha": "b" * 40}}}
            if path.startswith("git/trees/"):
                return {"tree": [{"path": "SPEC.md", "type": "blob", "mode": "100644", "sha": "c" * 40}]}
            if path.startswith("contents/"):
                spec = "Spec ID: `checkout`\n### US-01: View\nDepends on: None.\n### US-02: Order\nDepends on: US-01.\n"
                return {"type": "file", "encoding": "base64", "content": base64.b64encode(spec.encode()).decode()}
            if path.startswith("issues?"):
                assert path == "issues?state=open&per_page=100"
                return [self.issues]
            if path.startswith("labels?"):
                return [self.labels]
            if path == "labels":
                self.labels.append({"name": payload["name"]})
                return self.labels[-1]
            if path == "issues":
                number = len(self.issues) + 1
                issue = {**payload, "number": number, "html_url": f"https://github.com/Example/target/issues/{number}"}
                issue["labels"] = [{"name": label} for label in issue["labels"]]
                self.issues.append(issue)
                return issue
            number = int(path.split("/")[1])
            issue = self.issues[number - 1]
            issue["labels"].append({"name": "agent:implement"})
            return issue["labels"]

    boundary = Boundary()
    monkeypatch.setattr("software_factory.planning.publish.GitHub", lambda *args: boundary)
    monkeypatch.setattr("software_factory.planning.activate.GitHub", lambda *args: boundary)
    validate_plan(plan)
    publish(plan, True)
    assert not boundary.issues
    assert "[checkout/US-01] View" in capsys.readouterr().out
    publish(plan, False)
    assert len(boundary.issues) == 2
    publish(plan, False)
    assert len(boundary.issues) == 2
    activate(plan)
    assert all(any(label["name"] == "agent:implement" for label in issue["labels"]) for issue in boundary.issues)
    activate(plan)
    assert "already queued" in capsys.readouterr().out


@pytest.mark.skipif(os.environ.get("FACTORY_LIVE_PLANNING_TESTS") != "1", reason="explicit live GitHub test required")
def test_live_publish_and_activate() -> None:
    plan_path = Path(os.environ["FACTORY_LIVE_TEST_PLAN"])
    plan = json.loads(plan_path.read_text())
    validate_plan(plan)
    assert plan["repository"].lower() == "terots/factory-smoke-test"
    assert plan["spec_id"].startswith("e2e-") and plan["source"]["commit"] is not None
    issues = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", "repos/TeroTS/factory-smoke-test/issues?state=open&per_page=100"],
        capture_output=True,
        text=True,
        check=True,
    )
    for page in json.loads(issues.stdout):
        for issue in page:
            if "pull_request" not in issue:
                existing = metadata(issue, plan["repository"])
                assert existing is None or existing["spec_id"] != plan["spec_id"], "Use a fresh test spec ID"
    command = [sys.executable, "-m", "software_factory.planning"]

    def run(*args: str) -> str:
        result = subprocess.run(command + list(args) + ["--plan", str(plan_path)], capture_output=True, text=True)
        print(result.stdout, flush=True)
        assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
        return result.stdout

    preview = run("publish", "--dry-run")
    for story in plan["stories"]:
        assert f"[{plan['spec_id']}/{story['id']}] {story['title']}" in preview
    published = run("publish")
    assert published.count(": created #") == len(plan["stories"]), published
    created = re.findall(rf"{re.escape(plan['spec_id'])}/(US-\d+): created #(\d+)", published)
    assert len(created) == len(plan["stories"]) and len({number for _, number in created}) == len(created)
    assert run("publish").count(": existing #") == len(plan["stories"])
    activated = run("activate")
    assert activated.count(": queued #") == len(plan["stories"]), activated
    stories = {story["id"]: story for story in plan["stories"]}
    for identity, number in created:
        response = subprocess.run(
            ["gh", "api", f"repos/TeroTS/factory-smoke-test/issues/{number}"],
            capture_output=True,
            text=True,
            check=True,
        )
        issue = json.loads(response.stdout)
        story = stories[identity]
        assert issue["title"] == f"[{plan['spec_id']}/{identity}] {story['title']}"
        assert story["scope"] in issue["body"]
        assert all(item in issue["body"] for item in story["acceptance_criteria"] + story["verification"])
        assert "agent:implement" in {label["name"] for label in issue["labels"]}
    assert run("activate").count(": already queued #") == len(plan["stories"])
