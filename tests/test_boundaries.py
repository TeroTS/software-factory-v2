import json
from unittest.mock import Mock

import pytest

from software_factory.github import GitHub
from software_factory.process import FactoryError


@pytest.mark.parametrize(
    "operation,payload",
    [
        ("discover", [[{"number": "1; touch /tmp/bad"}]]),
        ("discover", [[{"number": -1}]]),
        ("discover", [[{"number": True}]]),
        ("discover", [None]),
        ("discover", [[None]]),
        ("open_pr", {}),
        ("open_pr", [[{"head": None}]]),
        ("open_pr", [[{"head": {"ref": "factory/issue-1", "repo": {"full_name": 3}}}]]),
        ("branch_exists", {}),
        ("branch_exists", [{"ref": None}]),
        ("remove_trigger", {}),
        ("remove_trigger", [{"name": None}]),
        ("snapshot", {}),
        ("snapshot", {"title": 1, "body": None}),
        ("snapshot", {"title": "task", "body": {}}),
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
