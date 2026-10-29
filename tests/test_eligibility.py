import json
import os
from unittest.mock import Mock

import pytest

from software_factory.config import Config
from software_factory.github import GitHub
from software_factory.planning.eligibility import eligible
from software_factory.planning.publish import render
from software_factory.process import FactoryError
from software_factory.runner import AgentRuntime, Runner


def ticket(number, story, dependencies=()):
    plan = {"spec_id": "shop", "repository": "owner/repo", "source": {"path": "SPEC.md", "commit": "a" * 40}}
    item = {
        "id": story,
        "title": "Task",
        "scope": "Do work",
        "acceptance_criteria": ["Done"],
        "verification": ["Test"],
        "depends_on": list(dependencies),
    }
    title, body = render(plan, item)
    return {
        "number": number,
        "title": title,
        "body": body,
        "labels": [{"name": "factory:generated"}, {"name": "agent:implement"}],
    }


def test_metadata_validation_does_not_fabricate_a_ticket_plan(monkeypatch):
    import software_factory.planning.publish as publication

    def reject_plan(_plan):
        raise AssertionError("metadata validation must not construct a ticket plan")

    monkeypatch.setattr(publication, "validate_plan", reject_plan, raising=False)
    data = publication.metadata(ticket(2, "US-02", ["US-01"]), "owner/repo")
    assert data["story_id"] == "US-02" and data["depends_on"] == ["US-01"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", True),
        ("repository", "other/repo"),
        ("spec_id", "Bad_ID"),
        ("story_id", "US-00"),
        ("source", {"path": "../SPEC.md", "commit": "a" * 40}),
        ("source", {"path": "SPEC.md", "commit": None}),
        ("depends_on", ["US-02"]),
        ("depends_on", ["US-01", "US-01"]),
        ("depends_on", ["US-00"]),
        ("depends_on", [None]),
    ],
)
def test_metadata_rejects_invalid_shared_fields(field, value):
    from software_factory.planning.publish import metadata

    issue = ticket(2, "US-02", ["US-01"])
    prefix, encoded = issue["body"].split("<!-- software-factory:planning\n")
    data = json.loads(encoded.split("\n")[0])
    data[field] = value
    issue["body"] = prefix + "<!-- software-factory:planning\n" + json.dumps(data) + "\n-->\n"
    with pytest.raises(FactoryError, match="Malformed generated issue metadata"):
        metadata(issue, "owner/repo")


def test_poll_skips_blocked_then_claims_independent_and_later_uses_checked_edit(tmp_path, monkeypatch):
    blocked = ticket(2, "US-02", ["US-01"])
    prerequisite = ticket(1, "US-01")
    independent = ticket(3, "US-03")
    state = {"issues": [blocked, independent, prerequisite], "merged": False, "claims": [], "executed": []}
    gh = GitHub("owner/repo", Mock())

    def api(path, **kwargs):
        if path.startswith("issues?state=open"):
            return [[{"number": 3}, {"number": 2}]]
        if path.startswith("issues?state=all"):
            return [state["issues"]]
        if path.startswith("issues/") and path.endswith("/labels/agent%3Aimplement"):
            state["claims"].append(int(path.split("/")[1]))
            return []
        if path.startswith("issues/") and path.endswith("/comments"):
            return {}
        if path.startswith("issues/"):
            return next(x.copy() for x in state["issues"] if x["number"] == int(path.split("/")[1]))
        if path.startswith("pulls?") or path.startswith("git/matching-refs/"):
            return [[]] if path.startswith("pulls?") else []
        if path == "":
            return {"default_branch": "main"}
        raise AssertionError(path)

    gh.api = api
    gh.closing_prs = lambda number: (
        [{"merged": state["merged"], "baseRefName": "main", "baseRepository": {"nameWithOwner": "owner/repo"}}]
    )
    monkeypatch.setattr("software_factory.runner.GitHub", lambda *args: gh)
    runner = Runner(Config("owner/repo", "model", "image", tmp_path), AgentRuntime("image", "unix:///socket"))
    monkeypatch.setattr(
        runner,
        "execute",
        lambda number, github, commands, directory, snapshot: (
            state["executed"].append(snapshot) or "https://github.com/owner/repo/pull/9"
        ),
    )
    runner.poll_once()
    assert state["claims"] == [3]
    assert state["executed"][0]["number"] == 3
    state["merged"] = True
    blocked["title"] = "Operator edited title"
    blocked["body"] += "Operator edited task\n"
    runner.poll_once()
    assert state["claims"] == [3, 2, 3]
    assert state["executed"][1]["title"] == "Operator edited title"
    assert state["executed"][1]["body"] == blocked["body"]


@pytest.mark.parametrize("damage", ["missing", "duplicate", "cycle", "bad-metadata", "invalid-duplicate", "lookup"])
def test_bad_dependency_data_fails_closed(damage):
    current = ticket(2, "US-02", ["US-01"])
    parent = ticket(1, "US-01")
    issues = [current, parent]
    if damage == "missing":
        issues.pop()
    elif damage == "duplicate":
        issues.append(ticket(4, "US-01"))
    elif damage == "cycle":
        issues[1] = ticket(1, "US-01", ["US-02"])
    elif damage == "bad-metadata":
        issues[1]["body"] = "private invalid content"
    elif damage == "invalid-duplicate":
        broken = ticket(4, "US-01")
        broken["body"] = broken["body"].replace('"version": 1', '"version": 2')
        issues.append(broken)
    gh = Mock(repository="owner/repo")
    gh.items.side_effect = lambda value, **kwargs: value[0]
    gh.api.side_effect = FactoryError("lookup failed") if damage == "lookup" else lambda *a, **k: [issues]
    with pytest.raises(FactoryError):
        eligible(gh, current)


def test_scripted_gh_boundary_checks_then_claims_only_independent_ticket(tmp_path, monkeypatch):
    from software_factory.process import Commands

    issues = [ticket(2, "US-02", ["US-01"]), ticket(1, "US-01"), ticket(3, "US-03")]
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"issues": issues, "claims": []}))
    executable = tmp_path / "gh"
    executable.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
assert os.environ["GH_TOKEN"] == "scoped-app"
file = Path(os.environ["GH_FIXTURE"])
state = json.loads(file.read_text())
args = sys.argv[1:]
endpoint = args[3]
method = args[args.index("--method") + 1]
if endpoint == "graphql":
    payload = json.load(sys.stdin)
    assert "includeClosedPrs: true" in payload["query"]
    assert payload["variables"]["number"] == 1
    connection = {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}
    result = {"data": {"repository": {"issue": {"closedByPullRequestsReferences": connection}}}}
elif endpoint.endswith("issues?state=open&labels=agent%3Aimplement&per_page=100"):
    result = [[{"number": 3}, {"number": 2}]]
elif endpoint.endswith("issues?state=all&per_page=100"):
    result = [state["issues"]]
elif endpoint.endswith("/pulls?state=open&head=owner%3Afactory%2Fissue-3&per_page=100"):
    result = [[]]
elif "git/matching-refs/" in endpoint:
    result = []
elif endpoint.endswith("/issues/3/labels/agent%3Aimplement") and method == "DELETE":
    state["claims"].append(3)
    result = []
elif endpoint.endswith("/issues/3/comments"):
    result = {}
elif endpoint.endswith("/issues/2") or endpoint.endswith("/issues/3"):
    number = int(endpoint.rsplit("/", 1)[1])
    result = next(issue for issue in state["issues"] if issue["number"] == number)
elif endpoint == "repos/owner/repo":
    result = {"default_branch": "main"}
else:
    raise AssertionError((endpoint, method))
file.write_text(json.dumps(state))
print(json.dumps(result))
""")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("GH_FIXTURE", str(state))
    auth = Mock()
    auth.environment.return_value = {**os.environ, "GH_TOKEN": "scoped-app"}
    runner = Runner(Config("owner/repo", "model", "image", tmp_path), AgentRuntime("image", "unix:///socket", auth))
    snapshots = []
    monkeypatch.setattr(
        runner,
        "execute",
        lambda number, github, commands, directory, snapshot: (
            snapshots.append(snapshot) or "https://github.com/owner/repo/pull/9"
        ),
    )
    runner.poll_once()
    assert json.loads(state.read_text())["claims"] == [3]
    assert snapshots == [{"number": 3, "title": issues[2]["title"], "body": issues[2]["body"]}]
    assert all(isinstance(call.args[0], Commands) for call in auth.environment.call_args_list)


def test_closing_pr_lookup_uses_app_and_paginates():
    commands = Mock()
    auth = Mock()
    auth.environment.return_value = {"GH_TOKEN": "app-token"}
    commands.run.side_effect = [
        json.dumps(
            {
                "data": {
                    "repository": {
                        "issue": {
                            "closedByPullRequestsReferences": {
                                "nodes": [],
                                "pageInfo": {"hasNextPage": True, "endCursor": "cursor"},
                            }
                        }
                    }
                }
            }
        ),
        json.dumps(
            {
                "data": {
                    "repository": {
                        "issue": {
                            "closedByPullRequestsReferences": {
                                "nodes": [
                                    {
                                        "merged": True,
                                        "baseRefName": "main",
                                        "baseRepository": {"nameWithOwner": "owner/repo"},
                                    }
                                ],
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                            }
                        }
                    }
                }
            }
        ),
    ]
    gh = GitHub("owner/repo", commands, auth)
    assert len(gh.closing_prs(1)) == 1
    calls = commands.run.call_args_list
    assert all(call.kwargs["env"] == {"GH_TOKEN": "app-token"} for call in calls)
    first = json.loads(calls[0].kwargs["input"])
    second = json.loads(calls[1].kwargs["input"])
    assert "includeClosedPrs: true" in first["query"]
    assert second["variables"]["cursor"] == "cursor"


def test_closing_pr_lookup_rejects_graphql_errors():
    commands = Mock()
    commands.run.return_value = json.dumps({"errors": [{"message": "private"}]})
    with pytest.raises(FactoryError, match="GitHub"):
        GitHub("owner/repo", commands).closing_prs(1)


def test_operator_dependency_edit_controls_eligibility():
    current = ticket(2, "US-02", ["US-01"])
    edited = ticket(2, "US-02")
    gh = Mock(repository="owner/repo")
    gh.api.return_value = [[current, ticket(1, "US-01")]]
    gh.items.side_effect = lambda value, **kwargs: value[0]
    gh.default_branch.return_value = "main"
    gh.closing_prs.return_value = []
    assert not eligible(gh, current)
    assert eligible(gh, edited)


@pytest.mark.parametrize(
    "response",
    [
        {"data": {"repository": None}},
        {
            "data": {
                "repository": {
                    "issue": {
                        "closedByPullRequestsReferences": {
                            "nodes": [],
                            "pageInfo": {"hasNextPage": True, "endCursor": None},
                        }
                    }
                }
            }
        },
        {
            "data": {
                "repository": {
                    "issue": {
                        "closedByPullRequestsReferences": {
                            "nodes": [{"merged": "yes"}],
                            "pageInfo": {"hasNextPage": False},
                        }
                    }
                }
            }
        },
    ],
)
def test_malformed_pr_evidence_is_error_not_completion(response):
    commands = Mock()
    commands.run.return_value = json.dumps(response)
    with pytest.raises(FactoryError, match="GitHub prerequisite lookup"):
        GitHub("owner/repo", commands).closing_prs(1)


def test_unrelated_invalid_ticket_does_not_block_independent_generated_work():
    current = ticket(2, "US-02")
    damaged = ticket(1, "US-01")
    damaged["body"] = "invalid"
    gh = Mock(repository="owner/repo")
    gh.api.return_value = [[current, damaged]]
    gh.items.side_effect = lambda value, **kwargs: value[0]
    assert eligible(gh, current)


def test_bad_ticket_logs_safe_error_and_continues_to_handwritten_issue(tmp_path, monkeypatch, caplog):
    invalid = ticket(1, "US-01")
    invalid["body"] = "private issue text"
    handwritten = {"number": 2, "title": "handwritten", "body": "task", "labels": [{"name": "agent:implement"}]}
    gh = Mock()
    gh.discover.return_value = [1, 2]
    gh.issue_for_eligibility.side_effect = [invalid, handwritten]
    gh.open_pr.return_value = "https://github.com/owner/repo/pull/9"
    monkeypatch.setattr("software_factory.runner.GitHub", lambda *args: gh)
    runner = Runner(Config("owner/repo", "model", "image", tmp_path), AgentRuntime("image", "unix:///socket"))
    runner.poll_once()
    gh.remove_trigger.assert_called_once_with(2)
    error = next(record for record in caplog.records if record.event == "issue_eligibility_failed")
    assert error.issue == 1 and error.repository == "owner/repo"
    assert "private issue text" not in caplog.text


def test_no_longer_labeled_issue_is_not_claimed(tmp_path, monkeypatch):
    gh = GitHub("owner/repo", Mock())
    gh.discover = lambda: [1]
    gh.issue_for_eligibility = lambda number: {"number": number, "title": "task", "body": None, "labels": []}
    gh.remove_trigger = Mock()
    monkeypatch.setattr("software_factory.runner.GitHub", lambda *args: gh)
    runner = Runner(Config("owner/repo", "model", "image", tmp_path), AgentRuntime("image", "unix:///socket"))
    runner.poll_once()
    gh.remove_trigger.assert_not_called()


def test_untrusted_metadata_and_handwritten_issues():
    gh = Mock(repository="owner/repo")
    handwritten = {"number": 9, "title": "Handwritten", "body": None, "labels": []}
    assert eligible(gh, handwritten)
    gh.api.assert_not_called()
    handwritten["labels"] = [{"name": "factory:generated"}]
    with pytest.raises(FactoryError):
        eligible(gh, handwritten)


@pytest.mark.parametrize(
    "merged,repo,branch,expected",
    [
        (False, "owner/repo", "main", False),
        (True, "other/repo", "main", False),
        (True, "owner/repo", "other", False),
        (True, "OWNER/REPO", "main", True),
    ],
)
def test_closing_pr_requires_merged_target_default_branch(merged, repo, branch, expected):
    current, parent = ticket(2, "US-02", ["US-01"]), ticket(1, "US-01")
    gh = Mock(repository="owner/repo")
    gh.api.return_value = [[current, parent]]
    gh.items.side_effect = lambda value, **kwargs: value[0]
    gh.default_branch.return_value = "main"
    gh.closing_prs.return_value = [{"merged": merged, "baseRefName": branch, "baseRepository": {"nameWithOwner": repo}}]
    assert eligible(gh, current) is expected
