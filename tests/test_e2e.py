import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from software_factory.config import load_config
from software_factory.github import GitHub
from software_factory.process import Commands
from software_factory.runner import Runner, preflight
from software_factory.sandbox import Sandbox, VerificationFailed

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
    assert set(github.discover()) <= {number}, (
        "remove other trigger labels before starting this dedicated end-to-end test"
    )
    assert github.open_pr(number) is None
    assert not github.branch_exists(number)
    issue = github.api(f"issues/{number}")
    assert issue["state"] == "open" and "pull_request" not in issue
    inspect = ["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project"]
    before = set(Commands().run(inspect, "inspect cleanup").splitlines())
    if not any(label["name"] == "agent:implement" for label in issue["labels"]):
        github.api(f"issues/{number}/labels", method="POST", payload={"labels": ["agent:implement"]})
    runner = Runner(config, prepared)
    verification_results = []
    original_verify = Sandbox.verify

    def observe_verification(sandbox):
        try:
            original_verify(sandbox)
        except VerificationFailed:
            verification_results.append(False)
            raise
        else:
            verification_results.append(True)

    with patch.object(Sandbox, "verify", observe_verification):
        for delay in (0, 30, 30):
            time.sleep(delay)
            assert set(github.discover()) <= {number}, "another issue was queued during the dedicated test"
            runner.poll_once()
            current = github.api(f"issues/{number}")
            if not any(label["name"] == "agent:implement" for label in current["labels"]):
                break
    url = github.open_pr(number)
    assert url is not None, "inspect issue status and private artifacts; do not blindly rerun live writes"
    pr = github.api("pulls/" + url.rsplit("/", 1)[1])
    assert pr["draft"] is True
    assert f"Closes #{number}" in pr["body"]
    comments = github.api(f"issues/{number}/comments?per_page=100", pages=True)
    assert any(comment["body"] == f"Succeeded: {url}" for page in comments for comment in page)
    assert number not in github.discover()
    assert set(Commands().run(inspect, "inspect cleanup").splitlines()) <= before
    if os.environ.get("FACTORY_E2E_REQUIRE_REPAIR") == "1":
        assert 2 <= len(verification_results) <= 4 and verification_results == [False] * (
            len(verification_results) - 1
        ) + [True], "repair recovery was not demonstrated; inspect the dedicated issue and PR before another live run"
    print(f"Issue https://github.com/{config.repository}/issues/{number} -> draft PR {url}")
