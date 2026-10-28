import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "172318459814.dkr.ecr.eu-central-1.amazonaws.com"
RUNNER = f"{REGISTRY}/software-factory-runner@sha256:" + "a" * 64
AGENT = f"{REGISTRY}/software-factory-agent@sha256:" + "b" * 64


@pytest.fixture
def selection(tmp_path: Path):
    tools = tmp_path / "bin"
    tools.mkdir()
    home = tmp_path / "home"
    state = home / ".config/software-factory"
    state.mkdir(parents=True, mode=0o700)
    selected = state / "deployment.env"
    selected.write_text("previous selection\n")
    config = state / "factory.toml"
    config.write_text("private operator configuration\n")
    diagnostics = home / "retained.log"
    diagnostics.write_text("private retained diagnostics\n")
    log = tmp_path / "commands.jsonl"
    stub = """#!/usr/bin/env python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
root = pathlib.Path(os.environ['TEST_ROOT'])
phase = os.environ.get('FAIL_PHASE', '')
with (root / 'commands.jsonl').open('a') as log:
    log.write(json.dumps({'tool':name, 'args':args, 'host':os.environ.get('DOCKER_HOST'),
        'context':os.environ.get('DOCKER_CONTEXT')}) + '\\n')
if name == 'id': print(os.environ.get('IDENTITY', '2000'))
elif name == 'systemctl':
    if phase == 'service-query': sys.exit(1)
    count = root / 'service-checked'
    active = phase == 'activated-during-check' and count.exists()
    count.touch()
    print('active' if active else os.environ.get('SERVICE', 'inactive'))
elif name == 'pgrep': sys.exit(int(os.environ.get('PGREP_STATUS', '1')))
elif name == 'timeout': os.execvp(args[1], args[1:])
elif name == 'mv':
    if phase == 'selection-write': sys.exit(1)
    os.execv('/bin/mv', ['mv', *args])
elif name == 'docker':
    assert os.environ.get('DOCKER_HOST') == 'unix:///var/run/docker.sock'
    assert 'DOCKER_CONTEXT' not in os.environ
    if args[0] == 'ps':
        if phase == 'container-query': sys.exit(1)
        print(os.environ.get('ACTIVE_CONTAINER', ''), end='')
    elif args[:2] == ['image', 'inspect']:
        kind = 'runner' if 'software-factory-runner@' in args[-1] else 'agent'
        if phase == 'inspect-' + kind: sys.exit(1)
        print(os.environ.get('PLATFORM', 'linux/arm64'))
    elif args[0] == 'run':
        assert '--pull=never' in args and '--network' in args and args[args.index('--network')+1] == 'none'
        assert '--mount' not in args and '--volume' not in args
        kind = 'runner' if any('software-factory-runner@' in a for a in args) else 'agent'
        cid = 'fixture-' + kind
        pathlib.Path(args[args.index('--cidfile')+1]).write_text(cid)
        (root / cid).write_text('probe')
        if phase == 'run-' + kind: sys.exit(1)
        print(cid)
    elif args[0] == 'exec':
        kind = args[1].removeprefix('fixture-')
        if phase == 'smoke-' + kind: sys.exit(1)
        if args[2] == 'python': print('agent-smoke')
        elif kind == 'runner': assert 'software_factory --help' in args[-1]
        else: assert args[-1] == 'agent-smoke'
    elif args[0] == 'rm':
        if phase == 'cleanup': sys.exit(1)
        (root / args[-1]).unlink(missing_ok=True)
    else: raise AssertionError(args)
"""
    for name in ("id", "systemctl", "pgrep", "timeout", "mv", "docker"):
        executable = tools / name
        executable.write_text(stub)
        executable.chmod(0o755)

    def run(*, fresh=False, **changes):
        if fresh:
            selected.unlink()
        section = (ROOT / "docs/operations.md").read_text().partition("### Stopped-host selection\n")[2]
        assert section, "The explicit stopped-host selection procedure is missing"
        procedure = section.split("```bash\n", 1)[1].split("```", 1)[0]
        env = {**os.environ, "PATH": f"{tools}:{os.environ['PATH']}", "HOME": str(home), "TEST_ROOT": str(tmp_path)}
        env.update(
            RUNNER_IMAGE=RUNNER, AGENT_IMAGE=AGENT, DOCKER_CONTEXT="must-ignore", DOCKER_HOST="tcp://must-ignore"
        )
        result = subprocess.run(
            ["bash", "-c", procedure], env={**env, **changes}, capture_output=True, text=True, timeout=60
        )
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        assert config.read_text() == "private operator configuration\n"
        assert diagnostics.read_text() == "private retained diagnostics\n"
        return result, selected, calls

    return run


@pytest.mark.parametrize("fresh", [False, True])
def test_selection_atomically_records_independent_digests_after_validation_and_cleanup(selection, fresh):
    result, selected, calls = selection(fresh=fresh)
    assert result.returncode == 0, result.stderr
    assert selected.read_text() == f"RUNNER_IMAGE={RUNNER}\nAGENT_IMAGE={AGENT}\n"
    assert selected.stat().st_mode & 0o777 == 0o600
    assert not list(selected.parent.glob(".selection.*"))
    assert not list(selected.parents[3].glob("fixture-*"))
    assert len([call for call in calls if call["tool"] == "systemctl"]) == 2
    assert len([call for call in calls if call["tool"] == "docker" and call["args"][0] == "rm"]) == 2
    assert calls[-1]["tool"] == "mv"


@pytest.mark.parametrize(
    "settings",
    [
        {"SERVICE": "active"},
        {"SERVICE": "activating"},
        {"SERVICE": "deactivating"},
        {"ACTIVE_CONTAINER": "running-container"},
        {"PGREP_STATUS": "0"},
        {"PGREP_STATUS": "2"},
        {"IDENTITY": "0"},
        {"RUNNER_IMAGE": "--unsafe"},
        {"AGENT_IMAGE": "registry/agent:mutable"},
        {"PLATFORM": "linux/amd64"},
        *[
            {"FAIL_PHASE": phase}
            for phase in (
                "service-query",
                "container-query",
                "inspect-runner",
                "inspect-agent",
                "run-runner",
                "run-agent",
                "smoke-runner",
                "smoke-agent",
                "cleanup",
                "selection-write",
                "activated-during-check",
            )
        ],
    ],
)
def test_failed_selection_preserves_previous_selection_and_private_state(selection, settings):
    result, selected, calls = selection(**settings)
    assert result.returncode != 0
    assert selected.read_text() == "previous selection\n"
    assert not any(call["tool"] == "mv" for call in calls) or settings == {"FAIL_PHASE": "selection-write"}
    if settings != {"FAIL_PHASE": "cleanup"}:
        assert not list(selected.parent.glob(".selection.*"))
        assert not list(selected.parents[3].glob("fixture-*"))


def test_failed_first_selection_remains_absent(selection):
    result, selected, _ = selection(fresh=True, FAIL_PHASE="smoke-agent")
    assert result.returncode != 0
    assert not selected.exists()
