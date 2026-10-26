import json
import os
from pathlib import Path

IMAGE = os.environ.get("FACTORY_AGENT_IMAGE", "software-factory-agent:1.0.0")


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
    assert instructions == pathlib.Path('/opt/software-factory/pi/AGENTS.md').read_bytes()
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
