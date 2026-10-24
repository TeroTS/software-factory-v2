import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from tests_support import IMAGE, target_repository

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        os.environ.get("FACTORY_DOCKER_TESTS") != "1",
        reason="set FACTORY_DOCKER_TESTS=1 and build the shared ARM64 image",
    ),
]


@pytest.mark.parametrize("outcome", ["success", "interruption", "inaccessible-file", "inaccessible-directory"])
def test_operator_labels_issue_and_observes_real_cli_docker_outcome(tmp_path: Path, outcome: str) -> None:
    source = tmp_path / "source"
    target_repository(source)
    if outcome == "interruption":
        setup = source / "scripts/setup"
        setup.write_text(setup.read_text() + "touch setup-ready\nsleep 60\ntouch too-late\n")
    elif outcome.startswith("inaccessible"):
        verify = source / "scripts/verify"
        command = (
            "sudo -n install -m 000 /dev/null inaccessible\n"
            if outcome == "inaccessible-file"
            else "mkdir inaccessible\nprintf required > inaccessible/required\nchmod 000 inaccessible\n"
        )
        verify.write_text(verify.read_text() + command)
    real_git = shutil.which("git")
    subprocess.run([real_git, "init", "-b", "main", str(source)], check=True, capture_output=True)
    for key, value in [("user.name", "Fixture"), ("user.email", "fixture@localhost")]:
        subprocess.run([real_git, "-C", str(source), "config", key, value], check=True)
    subprocess.run([real_git, "-C", str(source), "add", "."], check=True)
    subprocess.run([real_git, "-C", str(source), "commit", "-m", "fixture"], check=True, capture_output=True)
    remote = tmp_path / "origin.git"
    subprocess.run([real_git, "clone", "--bare", str(source), str(remote)], check=True, capture_output=True)
    tools = tmp_path / "tools"
    tools.mkdir()
    state_file = tmp_path / "github.json"
    # The operator applies the label to the scripted GitHub boundary; no authenticated service is contacted.
    state_file.write_text(json.dumps({"queued": True, "comments": [], "pr": None}))
    gh = tools / "gh"
    gh.write_text(
        f"#!{sys.executable}\n"
        + f"STATE={str(state_file)!r}\nREMOTE={str(remote)!r}\nGIT={real_git!r}\n"
        + f"STDERR={str(tmp_path / 'stderr')!r}\n"
        + """
import json, pathlib, re, subprocess, sys
args = sys.argv[1:]
if args[:2] == ['auth', 'status']: sys.exit(0)
assert args[:3] == ['api', '--hostname', 'github.com']
path = args[3].removeprefix('repos/owner/repo').lstrip('/')
method = args[args.index('--method')+1]
file = pathlib.Path(STATE)
state = json.loads(file.read_text())
payload = json.load(sys.stdin) if '--input' in args else None
if path.startswith('issues?'):
    result = [[{'number': 1}]] if state['queued'] else [[]]
elif path.startswith('pulls?'):
    result = [[]] if state['pr'] is None else [[{
        'head': {'ref':'factory/issue-1','repo':{'full_name':'owner/repo'}},'html_url':state['pr']}]]
elif path.startswith('git/matching-refs/'):
    exists = subprocess.check_output([GIT, '--git-dir='+REMOTE, 'show-ref'], text=True)
    result = [{'ref':'refs/heads/factory/issue-1'}] if 'refs/heads/factory/issue-1' in exists else []
elif path == 'issues/1/labels/agent%3Aimplement' and method == 'DELETE':
    state['queued'] = False
    result = []
elif path == 'issues/1/comments' and method == 'POST':
    state['comments'].append(payload['body'])
    result = {}
elif path == 'issues/1':
    result = {'title':'implement fixture','body':None}
elif path == '':
    result = {'default_branch':'main'}
elif path == 'pulls' and method == 'POST':
    assert payload == {'title':'implement fixture','head':'factory/issue-1',
                       'base':'main','body':'Closes #1','draft':True}
    # Check only this fixture's identity; unrelated factory runs are not our concern.
    log = pathlib.Path(STDERR).read_text()
    project = re.search(r'run identity (factory-[a-f0-9]{32})', log)[1]
    for kind in ('container','network','volume'):
        for label in ('software-factory.run-id', 'com.docker.compose.project'):
            check = ['docker',kind,'ls','--quiet','--filter',f'label={label}={project}']
            if kind == 'container': check.append('--all')
            assert not subprocess.check_output(check, text=True).strip()
    state['pr'] = 'https://github.com/owner/repo/pull/9'
    state['payload'] = payload
    result = {'html_url':state['pr']}
else:
    raise AssertionError((path, method, payload))
temporary = file.with_suffix('.tmp')
temporary.write_text(json.dumps(state))
temporary.replace(file)
print(json.dumps(result))
"""
    )
    gh.chmod(0o755)
    git = tools / "git"
    git.write_text(
        f"#!{sys.executable}\nimport os, sys\n"
        + f"args = [{real_git!r}, *sys.argv[1:]]\n"
        + f"args = [{str(remote)!r} if x == 'https://github.com/owner/repo.git' else x for x in args]\n"
        + f"os.execv({real_git!r}, args)\n"
    )
    git.chmod(0o755)
    pi = tools / "pi"
    pi.write_text(
        "#!/bin/sh\n[ \"$1 $2 $3\" = 'auth print-bearer-token --provider' ] || exit 99\n"
        + f"printf '%s\\n' 'proxy-ep=proxy.business.githubcopilot.com;exp={int(time.time()) + 1800}'\n"
    )
    pi.chmod(0o755)
    config = tmp_path / "operator.toml"
    config.write_text(f'repository="owner/repo"\nmodel="chosen"\nagent_image="{IMAGE}"\nartifacts_dir="runs"\n')
    previous = tmp_path / "runs/issue-1-previous-failure"
    previous.mkdir(parents=True)
    (previous / "run.log").write_text("previous private diagnostics\n")
    output = tmp_path / "stderr"
    with output.open("w") as stderr:
        process = subprocess.Popen(
            [sys.executable, "-m", "software_factory", "--config", str(config)],
            cwd=ROOT,
            env={**os.environ, "PATH": str(tools) + os.pathsep + os.environ["PATH"]},
            stderr=stderr,
            stdout=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                state = json.loads(state_file.read_text())
                directories = [p for p in previous.parent.iterdir() if p != previous]
                if outcome == "interruption" and directories and (directories[0] / "workspace/setup-ready").exists():
                    process.send_signal(signal.SIGTERM)
                    break
                failed = any(message.startswith("Failed:") for message in state["comments"])
                succeeded = any(message.startswith("Succeeded:") for message in state["comments"])
                # The success comment precedes optional artifact removal; do not interrupt that removal ourselves.
                if failed or (succeeded and not directories):
                    break
                assert process.poll() is None, output.read_text()
                time.sleep(0.1)
            else:
                pytest.fail("CLI did not finish the fixture run: " + output.read_text())
        finally:
            if process.poll() is None and outcome != "interruption":
                process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=30)
    state = json.loads(state_file.read_text())
    assert process.returncode == 130, output.read_text()
    assert not state["queued"]
    assert state["comments"][0] == "Running: implementation started"
    assert (previous / "run.log").read_text() == "previous private diagnostics\n"
    if outcome == "success":
        assert state["comments"][-1] == "Succeeded: https://github.com/owner/repo/pull/9", (state, output.read_text())
        content = subprocess.check_output(
            [real_git, "--git-dir=" + str(remote), "show", "factory/issue-1:site/index.html"], text=True
        )
        assert content == "implemented\n"
        assert state["payload"]["draft"] is True
        assert list(previous.parent.iterdir()) == [previous]
    else:
        assert state["pr"] is None
        if outcome == "interruption":
            assert state["comments"][-1] == "Failed: operator interruption", (state, output.read_text())
        else:
            assert state["comments"][-1].startswith("Failed:"), (state, output.read_text())
            assert "publication access" in state["comments"][-1] or "git add failed" in state["comments"][-1]
            assert (
                subprocess.run(
                    [real_git, "--git-dir=" + str(remote), "rev-parse", "--verify", "factory/issue-1"],
                    capture_output=True,
                ).returncode
                != 0
            )
        directory = next(p for p in previous.parent.iterdir() if p != previous)
        assert directory.stat().st_mode & 0o777 == 0o700
        assert (directory / "run.log").stat().st_mode & 0o777 == 0o600
        assert not (directory / "workspace/too-late").exists()
        if outcome.startswith("inaccessible"):
            restricted = directory / "workspace/inaccessible"
            assert restricted.stat().st_mode & 0o777 == 0
            # Dispose only this test fixture after asserting unchanged retained permissions.
            if restricted.is_dir():
                restricted.chmod(0o700)
            else:
                restricted.unlink()
    project = re.search(r"run identity (factory-[a-f0-9]{32})", output.read_text())[1]
    for kind in ("container", "network", "volume"):
        for label in ("software-factory.run-id", "com.docker.compose.project"):
            args = ["docker", kind, "ls", "--quiet", "--filter", f"label={label}={project}"]
            if kind == "container":
                args.append("--all")
            assert not subprocess.check_output(args, text=True).strip()
    subprocess.run(["docker", "image", "rm", "software-factory-fixture:" + project], capture_output=True)
