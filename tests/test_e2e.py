import os
from pathlib import Path

import pytest

from software_factory.config import load_config
from software_factory.github import GitHub
from software_factory.process import Commands
from software_factory.runner import Runner, preflight

pytestmark = pytest.mark.e2e


def test_operator_submits_issue_and_observes_linked_validated_draft_pr() -> None:
    config_path = os.environ.get("FACTORY_E2E_CONFIG")
    issue_input = os.environ.get("FACTORY_E2E_ISSUE")
    if not config_path or not issue_input or os.environ.get("FACTORY_E2E_APPROVED") != "1":
        pytest.skip("requires FACTORY_E2E_APPROVED=1, FACTORY_E2E_CONFIG, and a dedicated FACTORY_E2E_ISSUE")
    config = load_config(Path(config_path))
    assert config.repository == "TeroTS/factory-smoke-test", "live test is restricted to the smoke-test repository"
    number = int(issue_input)
    assert number > 0
    prepared = preflight(config)
    github = GitHub(config.repository, Commands())
    assert github.discover() == [], "remove other trigger labels before starting this dedicated end-to-end test"
    assert github.open_pr(number) is None
    assert not github.branch_exists(number)
    issue = github.api(f"issues/{number}")
    assert issue["state"] == "open" and "pull_request" not in issue
    inspect = ["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project"]
    before = set(Commands().run(inspect, "inspect cleanup").splitlines())
    github.api(f"issues/{number}/labels", method="POST", payload={"labels": ["agent:implement"]})
    Runner(config, prepared).poll_once()
    url = github.open_pr(number)
    assert url is not None, "inspect issue status and private artifacts; do not blindly rerun live writes"
    pr = github.api("pulls/" + url.rsplit("/", 1)[1])
    assert pr["draft"] is True
    assert f"Closes #{number}" in pr["body"]
    comments = github.api(f"issues/{number}/comments?per_page=100", pages=True)
    assert any(comment["body"] == f"Succeeded: {url}" for page in comments for comment in page)
    assert number not in github.discover()
    assert set(Commands().run(inspect, "inspect cleanup").splitlines()) <= before
    print(f"Issue https://github.com/{config.repository}/issues/{number} -> draft PR {url}")
