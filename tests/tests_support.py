import json
import os
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path

IMAGE = os.environ.get("FACTORY_AGENT_IMAGE", "software-factory-agent:1.0.0")


@contextmanager
def runner_container(config: Path, stderr):
    directory = config.parent
    home = directory / "home"
    credentials = home / ".config/software-factory"
    socket = Path("/var/run/docker.sock")
    name = "factory-runner-test-" + uuid.uuid4().hex
    subprocess.run(
        [
            "docker",
            "create",
            "--name",
            name,
            "--pull=never",
            "--platform",
            "linux/arm64",
            "--init",
            "--network",
            "none",
            "--label",
            "software-factory.runner=true",
            "--group-add",
            str(os.stat(socket).st_gid),
            "--mount",
            f"type=bind,src={socket},dst={socket}",
            "--mount",
            f"type=bind,src={directory},dst={directory}",
            "--mount",
            "type=bind,src=/home/factory/artifacts,dst=/home/factory/artifacts",
            "--mount",
            f"type=bind,src={credentials},dst={credentials},readonly",
            "--env",
            f"HOME={home}",
            "--env",
            "DOCKER_HOST=unix:///var/run/docker.sock",
            "--env",
            f"PATH={directory / 'tools'}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            os.environ.get("FACTORY_RUNNER_IMAGE", "software-factory-runner:test"),
            "--config",
            str(config),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        process = subprocess.Popen(["docker", "start", "--attach", name], stdout=subprocess.DEVNULL, stderr=stderr)
        try:
            yield process, name
        finally:
            if process.poll() is None:
                subprocess.run(["docker", "kill", "--signal", "TERM", name], capture_output=True)
            process.wait(timeout=120)
    finally:
        subprocess.run(["docker", "rm", "--force", name], check=True, capture_output=True)


def app_credentials(home: Path, tools: Path) -> None:
    directory = home / ".config/software-factory"
    directory.mkdir(parents=True, mode=0o700)
    config = directory / "github-app.json"
    config.write_text(json.dumps({"app_id": 123, "installation_id": 456}))
    config.chmod(0o600)
    key = directory / "github-app.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(key)],
        capture_output=True,
        check=True,
    )
    key.chmod(0o600)
    curl = tools / "curl"
    curl.write_text(
        "#!/usr/bin/env python3\n"
        "import datetime, json, os, sys\n"
        "settings = {k: json.loads(v) for k,v in (line.split(' = ',1) for line in sys.stdin.read().splitlines())}\n"
        "assert settings['url'] == 'https://api.github.com/app/installations/456/access_tokens'\n"
        "assert settings['header'].startswith('Authorization: Bearer ')\n"
        "assert len(settings['header'].split('.')) == 3\n"
        "assert 'GH_TOKEN' not in os.environ\n"
        "assert json.loads(settings['data'])['repositories'] == ['repo']\n"
        "assert sys.argv[1] == '--disable' and not any('Bearer' in arg for arg in sys.argv)\n"
        "print(json.dumps({'token':'fixture-installation-token',\n"
        "    'expires_at':(datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)).isoformat(),\n"
        "    'permissions':{'contents':'write','issues':'write','pull_requests':'write','metadata':'read'}}))\n"
    )
    curl.chmod(0o755)


def target_repository(workspace: Path) -> None:
    (workspace / "scripts").mkdir(parents=True)
    (workspace / "site").mkdir()
    (workspace / "site/index.html").write_text("before\n")
    (workspace / "fixture-tool").mkdir()
    (workspace / "fixture-tool/package.json").write_text(
        json.dumps(
            {
                "name": "factory-fixture-prerequisite",
                "version": "1.0.0",
                "bin": {"factory-fixture-prerequisite": "tool.js"},
            }
        )
    )
    tool = workspace / "fixture-tool/tool.js"
    tool.write_text("#!/usr/bin/env node\nconsole.log('target-installed');\n")
    tool.chmod(0o755)
    (workspace / "Dockerfile").write_text(f'FROM {IMAGE}\nWORKDIR /site\nCMD ["python","-m","http.server","8080"]\n')
    (workspace / ".dockerignore").write_text("*\n!Dockerfile\n")
    (workspace / "compose.yaml").write_text(
        json.dumps(
            {
                "services": {
                    "web": {
                        "build": ".",
                        "image": "software-factory-fixture:${FACTORY_RUN_ID}",
                        "user": "0:0",
                        "command": [
                            "sh",
                            "-ec",
                            "printf private > /data/private; chmod 600 /data/private; exec python -m http.server 8080",
                        ],
                        "volumes": ["./site:/site:ro", "data:/data", "./service-output:/output"],
                        "ports": ["127.0.0.1::8080"],
                        "healthcheck": {
                            "test": [
                                "CMD",
                                "python",
                                "-c",
                                "import urllib.request; urllib.request.urlopen('http://localhost:8080')",
                            ],
                            "interval": "1s",
                            "timeout": "2s",
                            "retries": 15,
                        },
                    }
                },
                "volumes": {"data": {}},
            }
        )
    )
    stub = """#!/usr/local/bin/python
import json, os, pathlib, sys
assert os.getuid() == os.getgid() == 2000
assert os.stat('/var/run/docker.sock').st_gid in os.getgroups()
if '--list-models' in sys.argv:
    print('github-copilot chosen 128k 4k')
else:
    home = pathlib.Path(os.environ['PI_CODING_AGENT_DIR'])
    instructions = (home / 'AGENTS.md').read_bytes()
    expected = pathlib.Path('/opt/software-factory/pi/AGENTS.md').read_bytes()
    paths = [pathlib.Path('/opt/software-factory/pi/skills') / name / 'SKILL.md'
             for name in ('test-driven-development', 'ponytail')]
    for path in paths:
        expected += (f'\\n\\n# Required factory skill\\nSource: {path}\\nBase directory: {path.parent}\\n\\n'.encode()
                     + path.read_bytes())
    assert instructions == expected
    assert [sys.argv[i+1] for i, arg in enumerate(sys.argv) if arg == '--skill'] == [str(path) for path in paths]
    assert '--no-skills' in sys.argv
    assert (paths[0].parent / 'testing-anti-patterns.md').read_text()
    assert b'Do not publish, commit, or push' in instructions
    assert '--no-context-files' not in sys.argv
    prompt = sys.stdin.read()
    assert 'Do not publish, commit, or push' not in prompt
    task = json.loads(prompt.split('Task snapshot:\\n', 1)[1])
    assert task['title'] == 'implement fixture'
    assert '--model' in sys.argv and sys.argv[sys.argv.index('--model')+1] == 'chosen'
    pathlib.Path('site/index.html').write_text('implemented\\n')
    pathlib.Path('private-file').write_text('host-writable\\n')
"""
    (workspace / "fixture-pi").write_text(stub)
    for name, body in {
        "setup": 'test "$(id -u):$(id -g)" = 2000:2000\n'
        'sudo -n sh -ec \'test "$HOME" = /root; test "$(id -u)" = 0\'\n'
        "npm install --global --ignore-scripts ./fixture-tool\n"
        'install -m 755 fixture-pi "$HOME/.local/bin/pi"\n'
        "mkdir -p service-output\n"
        "docker compose up --build --detach --wait\n"
        'docker network connect "${COMPOSE_PROJECT_NAME}_default" "$FACTORY_RUN_ID"\n'
        "docker compose exec -T --user 2000:2000 web sh -ec 'printf service-written > /output/owned'\n",
        "verify": 'test "$(id -u):$(id -g)" = 2000:2000\n'
        'test "$(factory-fixture-prerequisite)" = target-installed\n'
        'test "$(docker compose exec -T web stat -c %u:%a /data/private)" = 0:600\n'
        'test "$(stat -c %u:%g service-output/owned)" = 2000:2000\n'
        'test "$(cat service-output/owned)" = service-written\n'
        'test "$(uname -m)" = aarch64\n'
        "curl --fail --silent http://web:8080/ > service-response\n"
        "grep -qx implemented service-response\n",
    }.items():
        path = workspace / "scripts" / name
        path.write_text("#!/bin/sh\nset -eu\n" + body)
        path.chmod(0o755)
