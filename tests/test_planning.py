import copy
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from software_factory.planning import main, validate_plan
from software_factory.process import FactoryError


@pytest.fixture
def plan() -> dict:
    return {
        "version": 1,
        "repository": "Example/target",
        "spec_id": "checkout",
        "source": {"path": "SPEC.md", "commit": None},
        "stories": [
            {
                "id": "US-01",
                "title": "View checkout",
                "scope": "Show the checkout.",
                "acceptance_criteria": ["The total is visible."],
                "verification": ["Run checkout tests."],
                "depends_on": [],
            },
            {
                "id": "US-02",
                "title": "Place order",
                "scope": "Submit the checkout.",
                "acceptance_criteria": ["The order is placed."],
                "verification": ["Run order tests."],
                "depends_on": ["US-01"],
            },
        ],
    }


def test_github_dot_repository_is_valid(plan: dict) -> None:
    plan["repository"] = "Example/.github"
    validate_plan(plan)


def test_valid_draft_and_committed_plans(plan: dict) -> None:
    validate_plan(plan)
    for commit in ("a" * 40, "b" * 64):
        plan["source"]["commit"] = commit
        validate_plan(plan)


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.update(version=True),
        lambda p: p.update(extra=1),
        lambda p: p.update(repository="../target"),
        lambda p: p.update(repository="owner/repo/extra"),
        lambda p: p.update(repository="owner/repo name"),
        lambda p: p.update(repository="github.com/repo?query"),
        lambda p: p.update(spec_id="Bad_ID"),
        lambda p: p["source"].update(path="a/../SPEC.md"),
        lambda p: p["source"].update(path="/SPEC.md"),
        lambda p: p["source"].update(path="SPEC\x00.md"),
        lambda p: p["source"].update(commit="abcd"),
        lambda p: p.update(stories=[]),
        lambda p: p["stories"][0].update(id="US-00"),
        lambda p: p["stories"][0].update(title="  "),
        lambda p: p["stories"][0].update(scope="<!-- software-factory:planning"),
        lambda p: p["stories"][0].update(acceptance_criteria=[]),
        lambda p: p["stories"][0].update(verification=[123]),
        lambda p: p["stories"][0].update(depends_on=["US-99"]),
        lambda p: p["stories"][0].update(depends_on=["US-01"]),
        lambda p: p["stories"][0].update(depends_on=["US-02"]),
        lambda p: p["stories"][1].update(depends_on=["US-01", "US-01"]),
        lambda p: p["stories"][1].update(id="US-01"),
        lambda p: p["stories"][0].update(depends_on=[{}]),
    ],
)
def test_invalid_plans_are_rejected(plan: dict, change: Callable[[dict], None]) -> None:
    change(plan)
    with pytest.raises(FactoryError):
        validate_plan(plan)


def test_cli_validates_local_artifact_without_github_writes(tmp_path: Path, plan: dict) -> None:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    before = copy.deepcopy(plan)
    result = subprocess.run(
        [sys.executable, "-m", "software_factory.planning", "validate", "--plan", str(path)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert "valid" in result.stdout.lower()
    assert json.loads(path.read_text()) == before
    assert list(tmp_path.iterdir()) == [path]


def test_main_reports_validation_and_bad_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, plan: dict) -> None:
    path = tmp_path / "plan.json"
    monkeypatch.setattr(sys, "argv", ["planning", "validate", "--plan", str(path)])
    path.write_text(json.dumps(plan))
    assert main() == 0
    path.write_text('{"version": 1, "version": 1}')
    assert main() == 1
    path.write_text(json.dumps({**plan, "version": False}))
    assert main() == 1
    path.write_text("NaN")
    assert main() == 1
    path.unlink()
    assert main() == 1


def test_cli_interruption_returns_130(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["planning", "validate", "--plan", "plan.json"])

    def interrupted(*args: object, **kwargs: object) -> str:
        raise KeyboardInterrupt

    monkeypatch.setattr(Path, "read_text", interrupted)
    assert main() == 130


@pytest.mark.parametrize(
    "content", ['{"version": 1, "version": 1}', "{", "[]", "NaN", "\udcff", "[" * 2000 + "]" * 2000]
)
def test_cli_rejects_malformed_json_without_traceback(tmp_path: Path, content: str) -> None:
    path = tmp_path / "plan.json"
    path.write_bytes(content.encode("utf-8", errors="surrogateescape"))
    result = subprocess.run(
        [sys.executable, "-m", "software_factory.planning", "validate", "--plan", str(path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Traceback" not in result.stderr


def test_cli_rejects_missing_file_and_invalid_usage(tmp_path: Path) -> None:
    command = [sys.executable, "-m", "software_factory.planning"]
    missing = subprocess.run(
        command + ["validate", "--plan", str(tmp_path / "missing")], capture_output=True, text=True
    )
    usage = subprocess.run(command + ["validate"], capture_output=True, text=True)
    assert missing.returncode == 1
    assert "Traceback" not in missing.stderr
    assert usage.returncode == 2
