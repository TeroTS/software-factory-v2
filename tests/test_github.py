import json
from unittest.mock import Mock

import pytest


def github(responses: list):
    from software_factory.github import GitHub

    commands = Mock()
    commands.run.side_effect = [json.dumps(value) for value in responses]
    return GitHub("owner/repo", commands), commands


def test_discovery_paginates_and_excludes_pull_requests() -> None:
    gh, commands = github([[[{"number": 1}, {"number": 2, "pull_request": {}}], [{"number": 3}]]])
    assert gh.discover() == [1, 3]
    assert "--paginate" in commands.run.call_args.args[0]
    assert "--slurp" in commands.run.call_args.args[0]


@pytest.mark.parametrize("head_repo", ["owner/repo", "other/repo"])
@pytest.mark.parametrize("head_branch", ["factory/issue-1", "factory/issue-10"])
def test_duplicate_pr_uses_exact_head_repository_and_branch(head_repo: str, head_branch: str) -> None:
    gh, _ = github(
        [
            [
                [
                    {
                        "head": {"repo": {"full_name": head_repo}, "ref": head_branch},
                        "html_url": "https://github.com/owner/repo/pull/9",
                    }
                ]
            ]
        ]
    )
    expected = (
        "https://github.com/owner/repo/pull/9"
        if (head_repo, head_branch) == ("owner/repo", "factory/issue-1")
        else None
    )
    assert gh.open_pr(1) == expected


def test_branch_identity_is_exact_and_read_failure_is_not_absence() -> None:
    from software_factory.process import FactoryError

    gh, commands = github([[{"ref": "refs/heads/factory/issue-10"}], [{"ref": "refs/heads/factory/issue-1"}]])
    assert not gh.branch_exists(1)
    assert gh.branch_exists(1)
    commands.run.side_effect = FactoryError("GitHub read failed")
    with pytest.raises(FactoryError):
        gh.branch_exists(1)


def test_label_removal_is_confirmed() -> None:
    from software_factory.process import FactoryError

    gh, _ = github([[{"name": "other"}], [{"name": "agent:implement"}]])
    gh.remove_trigger(1)
    with pytest.raises(FactoryError, match="label removal"):
        gh.remove_trigger(1)


def test_snapshot_fetches_only_title_body_number_and_comments_are_stdin_json() -> None:
    gh, commands = github([{"number": 1, "title": "$(attack)", "body": None, "comments_url": "ignored"}, {}])
    assert gh.snapshot(1) == {"number": 1, "title": "$(attack)", "body": None}
    gh.comment(1, "private-looking $(text)")
    call = commands.run.call_args
    assert "$(text)" not in " ".join(call.args[0])
    assert json.loads(call.kwargs["input"]) == {"body": "private-looking $(text)"}


def test_draft_pr_contains_issue_link_and_returns_actual_url() -> None:
    gh, commands = github([{"html_url": "https://github.com/owner/repo/pull/9"}])
    assert gh.publish(1, "Title", "main") == "https://github.com/owner/repo/pull/9"
    payload = json.loads(commands.run.call_args.kwargs["input"])
    assert payload == {"title": "Title", "head": "factory/issue-1", "base": "main", "body": "Closes #1", "draft": True}


def test_default_branch_is_read_from_github() -> None:
    gh, commands = github([{"default_branch": "trunk"}])
    assert gh.default_branch() == "trunk"
    assert "repos/owner/repo" in commands.run.call_args.args[0]


@pytest.mark.parametrize("value", [{}, {"html_url": "https://attacker.com/pr"}])
def test_publication_requires_actual_valid_pr_url(value: dict) -> None:
    from software_factory.process import FactoryError

    gh, _ = github([value])
    with pytest.raises(FactoryError):
        gh.publish(1, "Title", "main")


@pytest.mark.parametrize("payload", ["not-json", "{}"])
def test_bad_discovery_response_fails_visibly(payload: str) -> None:
    from software_factory.github import GitHub
    from software_factory.process import Commands, FactoryError

    commands = Mock(spec=Commands)
    commands.run.return_value = payload
    with pytest.raises(FactoryError, match="GitHub"):
        GitHub("owner/repo", commands).discover()
