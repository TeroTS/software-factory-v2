import json
import os
import subprocess
from pathlib import Path

import pytest
from tests_support import app_credentials

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        os.environ.get("FACTORY_RUNNER_IMAGE_TESTS") != "1",
        reason="build runner/agent images on the native guest and set FACTORY_RUNNER_IMAGE_TESTS=1",
    ),
]


def test_runner_container_executes_bridge_in_sibling_and_preserves_private_state(tmp_path: Path):
    assert (os.geteuid(), os.getegid()) == (2000, 2000)
    home = tmp_path / "home"
    tools = tmp_path / "tools"
    tools.mkdir()
    app_credentials(home, tools)
    credentials = home / ".config/software-factory"
    pi = home / ".pi/agent"
    pi.mkdir(parents=True, mode=0o700)
    (pi / "auth.json").write_text("private-fixture")
    (pi / "auth.json").chmod(0o600)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    socket = Path("/var/run/docker.sock")
    runner = os.environ.get("FACTORY_RUNNER_IMAGE", "software-factory-runner:test")
    agent = os.environ.get("FACTORY_AGENT_IMAGE", "software-factory-agent:1.0.0")
    script = r'''
import os, time
from pathlib import Path
from software_factory.auth import GitHubApp
from software_factory.process import Commands
from software_factory.sandbox import Sandbox
root = Path(os.environ['TEST_ROOT'])
auth = GitHubApp.load('owner/repo')
try:
    auth.key.write_text('must-not-overwrite')
except OSError:
    pass
else:
    raise AssertionError('App credentials must be read-only')
pi = Path.home() / '.pi/agent/auth.json'
assert pi.stat().st_mode & 0o777 == 0o600
pi.write_text('refreshed-private-fixture')
commands = Commands(deadline=time.monotonic() + 120, log=root / 'run.log')
commands.secrets.append('fixture-only')
sandbox = Sandbox(os.environ['TEST_AGENT'], 'unix:///var/run/docker.sock', root, commands)
try:
    sandbox.start()
    stub = """#!/usr/local/bin/python
import sys
from pathlib import Path
if '--list-models' in sys.argv:
    print('github-copilot chosen 128k 4k')
else:
    assert 'Task snapshot:' in sys.stdin.read()
    Path('outcome').write_text('implemented through runner bridge')
"""
    commands.run(sandbox.base + ['sudo', '-n', 'tee', '/usr/local/bin/pi'], 'scripted Pi', input=stub)
    commands.run(sandbox.base + ['sudo', '-n', 'chmod', '755', '/usr/local/bin/pi'], 'scripted Pi mode')
    sandbox.implement(
        {'title':'fixture', 'body':'fixture'}, 'fixture-only', 'https://api.individual.githubcopilot.com', 'chosen'
    )
    assert (sandbox.workspace / 'outcome').read_text() == 'implemented through runner bridge'
    assert (sandbox.workspace / 'outcome').stat().st_uid == 2000
finally:
    sandbox.stop()
'''
    args = [
        "docker",
        "run",
        "--rm",
        "--pull=never",
        "--platform",
        "linux/arm64",
        "--group-add",
        str(socket.stat().st_gid),
        "--mount",
        f"type=bind,src={socket},dst={socket}",
        "--mount",
        f"type=bind,src={tmp_path},dst={tmp_path}",
        "--mount",
        f"type=bind,src={credentials},dst=/home/factory/.config/software-factory,readonly",
        "--mount",
        f"type=bind,src={pi},dst=/home/factory/.pi/agent",
        "--env",
        f"TEST_ROOT={tmp_path}",
        "--env",
        f"TEST_AGENT={agent}",
        "--entrypoint",
        "python",
        runner,
        "-c",
        script,
    ]
    result = subprocess.run(args, text=True, capture_output=True, timeout=180)
    assert result.returncode == 0, result.stderr
    assert "private-fixture" not in result.stdout + result.stderr
    assert (pi / "auth.json").read_text() == "refreshed-private-fixture"
    assert json.loads((credentials / "github-app.json").read_text())["app_id"] == 123
