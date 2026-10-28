import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "172318459814.dkr.ecr.eu-central-1.amazonaws.com"


@pytest.fixture
def publisher(tmp_path):
    tools = tmp_path / "bin"
    tools.mkdir()
    log = tmp_path / "commands.jsonl"
    stub = """#!/usr/bin/env python3
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['COMMAND_LOG'], 'a') as log:
    log.write(json.dumps({'tool':name, 'args':args, 'auth':os.environ.get('DOCKER_CONFIG'),
        'aws_env':{k:os.environ.get(k) for k in ('AWS_PROFILE','AWS_REGION','AWS_DEFAULT_REGION')}}) + '\\n')
phase = name + ' ' + ' '.join(args[:2])
if phase.startswith(os.environ.get('FAIL_PHASE', '!')):
    sys.exit(1)
if name == 'aws':
    if 'get-caller-identity' in args: print(os.environ.get('ACCOUNT', '172318459814'))
    else: print('fixture-password')
elif name == 'docker':
    if args[0] == 'context': print('unix:///var/run/docker.sock')
    elif args[0] == 'info': print(os.environ.get('ENGINE', 'linux/aarch64'))
    elif args[:2] == ['image', 'inspect']:
        print('sha256:' + 'a' * 64 if '.Id' in args[-2] else 'linux/arm64')
    elif args[0] == 'login':
        assert sys.stdin.read().strip() == 'fixture-password'
        auth = pathlib.Path(os.environ['DOCKER_CONFIG'])
        assert auth.stat().st_mode & 0o777 == 0o700
        (auth / 'config.json').write_text('fixture-private-login')
elif name == 'git': print('a' * 40)
elif name == 'uv': print('agent-smoke')
"""
    for tool in ("aws", "docker", "git", "uv"):
        executable = tools / tool
        executable.write_text(stub)
        executable.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith("DOCKER_")}
    env.update(PATH=f"{tools}:{env['PATH']}", COMMAND_LOG=str(log))

    def run(*args, **changes):
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/publish-image"), *args], env={**env, **changes}, capture_output=True, text=True
        )
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return result, calls

    return run


@pytest.mark.parametrize("kind,version", [("runner", "runner-v1"), ("agent", "agent-v2")])
def test_publish_builds_tests_and_pushes_only_chosen_image(publisher, kind, version):
    result, calls = publisher(kind, version)
    assert result.returncode == 0, result.stderr
    image = f"{REGISTRY}/software-factory-{kind}:{version}"
    docker = [c for c in calls if c["tool"] == "docker"]
    assert [c["args"] for c in docker if c["args"][0] == "push"] == [["push", image]]
    build = next(c["args"] for c in docker if c["args"][0] == "build")
    assert build[build.index("--platform") + 1] == "linux/arm64"
    assert build[-1] == ("agent" if kind == "agent" else ".")
    assert next(i for i, c in enumerate(docker) if c["args"][0] == "run") < next(
        i for i, c in enumerate(docker) if c["args"][0] == "push"
    )
    login = next(c for c in docker if c["args"][0] == "login")
    assert "--password-stdin" in login["args"]
    assert not Path(login["auth"]).exists()
    assert "fixture-password" not in result.stdout + result.stderr


@pytest.mark.parametrize("args", [(), ("runner",), ("other", "v1"), ("agent", "../bad"), ("runner", "v1;echo")])
def test_bad_publication_arguments_do_not_contact_boundaries(publisher, args):
    result, calls = publisher(*args)
    assert result.returncode != 0
    assert not calls


@pytest.mark.parametrize(
    "settings", [{"ACCOUNT": "wrong"}, {"ENGINE": "linux/amd64"}, {"DOCKER_HOST": "tcp://remote:2375"}]
)
def test_wrong_account_or_engine_never_builds(publisher, settings):
    result, calls = publisher("runner", "v1", **settings)
    assert result.returncode != 0
    assert not any(c["tool"] == "docker" and c["args"][0] == "build" for c in calls)


def test_publication_preserves_operator_aws_environment(publisher):
    settings = {"AWS_PROFILE": "operator-profile", "AWS_REGION": "eu-central-1", "AWS_DEFAULT_REGION": "eu-central-1"}
    result, calls = publisher("runner", "v1", **settings)
    assert result.returncode == 0, result.stderr
    assert all(c["aws_env"] == settings for c in calls if c["tool"] == "aws")


def test_explicit_context_overrides_inherited_remote_host(publisher):
    result, calls = publisher("runner", "v1", DOCKER_CONTEXT="local", DOCKER_HOST="tcp://remote:2375")
    assert result.returncode == 0, result.stderr
    assert any(c["tool"] == "docker" and c["args"][0] == "context" for c in calls)


@pytest.mark.parametrize("phase", ["aws sts", "docker build", "docker run", "aws ecr", "docker login"])
def test_failed_preparation_never_pushes_and_removes_temporary_login(publisher, phase):
    result, calls = publisher("runner", "v1", FAIL_PHASE=phase)
    assert result.returncode != 0
    assert not any(c["tool"] == "docker" and c["args"][0] == "push" for c in calls)
    assert all(not Path(c["auth"]).exists() for c in calls if c["tool"] == "docker" and c["args"][0] == "login")


def test_runner_build_is_allowlisted_and_has_native_ubuntu_identity():
    dockerfile = (ROOT / "runner/Dockerfile").read_text()
    assert "FROM ubuntu:24.04@sha256:" in dockerfile
    assert "USER factory:factory" in dockerfile
    assert 'ENTRYPOINT ["python", "-m", "software_factory"]' in dockerfile
    assert "COPY src/software_factory /opt/software-factory/src/software_factory" in dockerfile
    ignore = (ROOT / ".dockerignore").read_text().splitlines()
    assert ignore[0] == "**"
    assert not any("artifacts" in line and line.startswith("!") for line in ignore)
