import os
import subprocess
import time
from pathlib import Path

import pytest


def git(path: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(path), *args], text=True, stderr=subprocess.DEVNULL).strip()


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    path = tmp_path / "origin"
    path.mkdir()
    git(path, "init", "-b", "main")
    git(path, "config", "user.name", "Test")
    git(path, "config", "user.email", "test@localhost")
    (path / "hello.txt").write_text("base\n")
    git(path, "add", ".")
    git(path, "commit", "-m", "base")
    return path


def test_fresh_workspace_and_host_owned_metadata(origin: Path, tmp_path: Path) -> None:
    from software_factory.process import Commands, FactoryError
    from software_factory.repository import Repository

    directory = tmp_path / "run"
    directory.mkdir()
    repo = Repository(directory, Commands(time.monotonic() + 20))
    base = repo.checkout(str(origin), "main")
    assert base == git(origin, "rev-parse", "HEAD")
    assert (repo.workspace / "hello.txt").read_text() == "base\n"
    assert not (repo.workspace / ".git").exists()
    with pytest.raises(FactoryError, match="no changes produced"):
        repo.commit(1)
    (repo.workspace / "hello.txt").write_text("changed\n")
    commit = repo.commit(1)
    assert commit != base
    assert repo.git("show", "HEAD:hello.txt").strip() == "changed"


def test_sandbox_git_hooks_filters_helpers_and_host_git_env_cannot_execute(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from software_factory.process import Commands
    from software_factory.repository import Repository

    marker = tmp_path / "executed"
    attack = f"!touch {marker}"
    global_config = tmp_path / "global.gitconfig"
    global_config.write_text(f'[filter "attack"]\nclean = {attack}\n[core]\nfsmonitor = {attack}\n')
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", attack)
    directory = tmp_path / "run"
    directory.mkdir()
    repo = Repository(directory, Commands())
    repo.checkout(str(origin), "main")
    malicious = repo.workspace / ".git"
    malicious.mkdir()
    (malicious / "config").write_text(f'[core]\nhooksPath = {tmp_path}\n[filter "attack"]\nclean = {attack}\n')
    hook = tmp_path / "pre-commit"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n")
    hook.chmod(0o755)
    (repo.workspace / ".gitattributes").write_text("*.txt filter=attack\n")
    (repo.workspace / "hello.txt").write_text("safe\n")
    (repo.workspace / "link").symlink_to(tmp_path / "outside-private")
    (tmp_path / "outside-private").write_text("not committed")
    repo.commit(1)
    assert not marker.exists()
    assert repo.git("show", "HEAD:link").strip() == str(tmp_path / "outside-private")
    assert "outside-private" not in repo.git("ls-tree", "--name-only", "HEAD").splitlines()


def test_push_creates_new_branch_but_never_overwrites_existing(origin: Path, tmp_path: Path) -> None:
    from software_factory.process import Commands, FactoryError
    from software_factory.repository import Repository

    directory = tmp_path / "run"
    directory.mkdir()
    repo = Repository(directory, Commands())
    repo.checkout(str(origin), "main")
    (repo.workspace / "hello.txt").write_text("change\n")
    first = repo.commit(2)
    repo.push(str(origin), 2)
    assert git(origin, "rev-parse", "factory/issue-2") == first
    (repo.workspace / "hello.txt").write_text("second\n")
    repo.commit(2)
    with pytest.raises(FactoryError, match="branch already exists"):
        repo.push(str(origin), 2)
    assert git(origin, "rev-parse", "factory/issue-2") == first


def test_push_rejects_branch_created_after_absence_check(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from software_factory.process import Commands, FactoryError
    from software_factory.repository import Repository

    directory = tmp_path / "run"
    directory.mkdir()
    repo = Repository(directory, Commands())
    base = repo.checkout(str(origin), "main")
    (repo.workspace / "hello.txt").write_text("change\n")
    repo.commit(2)
    original_git = repo.git

    def create_branch_after_check(*args: str) -> str:
        output = original_git(*args)
        if args[0] == "ls-remote":
            assert not output.strip()
            git(origin, "branch", "factory/issue-2", base)
        return output

    monkeypatch.setattr(repo, "git", create_branch_after_check)
    with pytest.raises(FactoryError, match="git push failed"):
        repo.push(str(origin), 2)
    assert git(origin, "rev-parse", "factory/issue-2") == base


def test_nested_git_metadata_is_rejected_before_host_staging(origin: Path, tmp_path: Path) -> None:
    from software_factory.process import Commands, FactoryError
    from software_factory.repository import Repository

    directory = tmp_path / "run"
    directory.mkdir()
    repo = Repository(directory, Commands())
    repo.checkout(str(origin), "main")
    nested = repo.workspace / "vendor" / ".git"
    nested.parent.mkdir()
    nested.write_text("gitdir: /private/host/repository\n")
    with pytest.raises(FactoryError, match="nested Git metadata"):
        repo.commit(1)


@pytest.mark.parametrize("mode", [0o000, 0o400])
def test_inaccessible_required_directory_blocks_commit_without_repair(origin: Path, tmp_path: Path, mode: int) -> None:
    from software_factory.process import Commands, FactoryError
    from software_factory.repository import Repository

    assert os.getuid() != 0, "run access regressions as a normal host user"
    run = tmp_path / "run"
    run.mkdir()
    repo = Repository(run, Commands())
    repo.checkout(str(origin), "main")
    (repo.workspace / "hello.txt").write_text("changed\n")
    private = repo.workspace / "private"
    private.mkdir()
    (private / "required.txt").write_text("must not be silently skipped")
    private.chmod(mode)
    try:
        with pytest.raises(FactoryError, match="publication access"):
            repo.commit(1)
        assert private.stat().st_mode & 0o777 == mode
        assert repo.git("rev-parse", "HEAD").strip() == git(origin, "rev-parse", "HEAD")
    finally:
        private.chmod(0o700)


def test_ignored_inaccessible_cache_does_not_block_publication(origin: Path, tmp_path: Path) -> None:
    from software_factory.process import Commands
    from software_factory.repository import Repository

    run = tmp_path / "run"
    run.mkdir()
    repo = Repository(run, Commands())
    repo.checkout(str(origin), "main")
    (repo.workspace / ".gitignore").write_text("cache/\n")
    cache = repo.workspace / "cache"
    cache.mkdir()
    (cache / "unused").write_text("ignored")
    cache.chmod(0o000)
    try:
        repo.commit(1)
        assert cache.stat().st_mode & 0o777 == 0
        assert repo.git("show", "HEAD:.gitignore").strip() == "cache/"
    finally:
        cache.chmod(0o700)


def test_ignored_directory_with_tracked_content_is_not_skipped(origin: Path, tmp_path: Path) -> None:
    from software_factory.process import Commands, FactoryError
    from software_factory.repository import Repository

    run = tmp_path / "run"
    run.mkdir()
    repo = Repository(run, Commands())
    repo.checkout(str(origin), "main")
    folder = repo.workspace / "tracked"
    folder.mkdir()
    (folder / "source").write_text("tracked content")
    repo.commit(1)
    (repo.workspace / ".gitignore").write_text("tracked/\n")
    folder.chmod(0o000)
    try:
        with pytest.raises(FactoryError, match="publication access"):
            repo.commit(1)
    finally:
        folder.chmod(0o700)


def test_missing_remote_ref_is_a_failure(origin: Path, tmp_path: Path) -> None:
    from software_factory.process import Commands, FactoryError
    from software_factory.repository import Repository

    run = tmp_path / "run"
    run.mkdir()
    with pytest.raises(FactoryError):
        Repository(run, Commands()).checkout(str(origin), "missing")
