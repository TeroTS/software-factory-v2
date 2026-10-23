import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from software_factory.github import GitHub
from software_factory.process import FactoryError
from software_factory.sandbox import prepare_compose


@pytest.mark.parametrize(
    "operation,payload",
    [
        ("discover", [[{"number": "1; touch /tmp/bad"}]]),
        ("discover", [[{"number": -1}]]),
        ("discover", [[{"number": True}]]),
        ("discover", [None]),
        ("open_pr", {}),
        ("open_pr", [[{"head": None}]]),
        ("branch_exists", {}),
        ("branch_exists", [{"ref": None}]),
        ("remove_trigger", {}),
        ("remove_trigger", [{"name": None}]),
        ("snapshot", {}),
        ("snapshot", {"title": 1, "body": None}),
        ("default_branch", {}),
        ("default_branch", {"default_branch": ""}),
        ("publish", []),
    ],
)
def test_github_malformed_responses_fail_closed(operation: str, payload) -> None:
    commands = Mock()
    commands.run.return_value = json.dumps(payload)
    github = GitHub("owner/repo", commands)
    args = (
        () if operation in {"discover", "default_branch"} else (1, "title", "main") if operation == "publish" else (1,)
    )
    with pytest.raises(FactoryError, match="GitHub"):
        getattr(github, operation)(*args)


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {"services": []},
        {"services": {"agent": None}},
        {"services": {"agent": {"image": "test", "volumes": ["/host:/workspace"]}}},
    ],
)
def test_malformed_compose_fails_with_safe_diagnostic(tmp_path: Path, data) -> None:
    with pytest.raises(FactoryError, match="Compose"):
        prepare_compose(data, "agent", tmp_path)


def test_compose_environment_reinterpolation_cannot_read_host_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests_support import prepared_compose

    from software_factory.sandbox import Sandbox

    monkeypatch.setenv("GH_TOKEN", "host-secret")
    commands = Mock()
    sandbox = Sandbox(prepared_compose(tmp_path), "agent", tmp_path, commands)
    sandbox.start()
    assert "GH_TOKEN" not in commands.run.call_args.kwargs["env"]
