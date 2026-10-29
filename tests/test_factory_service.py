import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "infra/ec2/scripts/factory"
RUNNER = "172318459814.dkr.ecr.eu-central-1.amazonaws.com/software-factory-runner@sha256:" + "a" * 64
AGENT = "172318459814.dkr.ecr.eu-central-1.amazonaws.com/software-factory-agent@sha256:" + "b" * 64
RUNNER_ID = "sha256:" + "c" * 64


def launch(
    tmp_path: Path, failure: str = "", runner: str = RUNNER, agent: str = AGENT
) -> tuple[subprocess.CompletedProcess, list, Path]:
    home = tmp_path / "home"
    state = home / ".config/software-factory"
    state.mkdir(parents=True, mode=0o700)
    (state / "deployment.env").write_text(f"RUNNER_IMAGE={runner}\nAGENT_IMAGE={agent}\n")
    (state / "factory.toml").write_text("private configuration fixture")
    pi = home / ".pi/agent"
    pi.mkdir(parents=True, mode=0o700)
    calls = tmp_path / "calls.jsonl"
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    harness = r"""
set -euo pipefail
id() { if [ "$1" = -u ]; then echo 2000; else echo 2000; fi; }
stat() { if [ "${*: -1}" = /var/run/docker.sock ]; then echo 998; else command stat "$@"; fi; }
pgrep() { if [ "$FAILURE" = native ]; then return 0; else return 1; fi; }
mkdir() {
  if [ "${*: -1}" = /home/factory/artifacts ]; then command mkdir -p "$TEST_ARTIFACTS"
  else command mkdir "$@"; fi
}
docker() { python3 "$STUB" "$@"; }
systemd-notify() { if [ "$FAILURE" = notify ]; then return 1; fi; printf '%s\n' "$*" > "$NOTIFIED"; }
export -f id stat pgrep mkdir docker systemd-notify
source "$LAUNCHER"
"""
    stub = tmp_path / "docker.py"
    stub.write_text("""import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ['CALLS'], 'a') as log:
    log.write(json.dumps(args) + '\\n')
failure = os.environ['FAILURE']
if 'ps' in args:
    if failure == 'inspection': sys.exit(1)
    if failure == 'active': print('existing-runner')
elif 'inspect' in args:
    if failure == 'missing-runner' and args[-1] == os.environ['RUNNER_IMAGE']: sys.exit(1)
    if failure == 'missing-agent' and args[-1] == os.environ['AGENT_IMAGE']: sys.exit(1)
    platform = 'linux/amd64' if failure == 'platform' else 'linux/arm64'
    image_id = 'bad-id' if failure == 'image-id' else 'sha256:' + 'c' * 64
    print(platform + (' ' + image_id if '{{.Id}}' in args[args.index('--format') + 1] else ''))
else:
    failed = failure in {'startup', 'config'}
    print(json.dumps({'event': 'runner_failed' if failed else 'runner_polling'}), file=sys.stderr)
    sys.exit(1 if failed else 0)
""")
    result = subprocess.run(
        ["bash", "-c", harness],
        env={
            **os.environ,
            "HOME": str(home),
            "LAUNCHER": str(SCRIPTS / "start-runner.sh"),
            "STUB": str(stub),
            "CALLS": str(calls),
            "TEST_ARTIFACTS": str(home / "artifacts"),
            "FAILURE": failure,
            "RUNTIME_DIRECTORY": str(runtime),
            "NOTIFY_SOCKET": "fixture-notify-socket",
            "NOTIFIED": str(tmp_path / "notified"),
            "RUNNER_IMAGE": runner,
            "AGENT_IMAGE": agent,
        },
        text=True,
        capture_output=True,
        timeout=10,
    )
    return result, [json.loads(line) for line in calls.read_text().splitlines()] if calls.exists() else [], home


@pytest.mark.parametrize(
    "runner,agent",
    [
        (RUNNER, AGENT),
        ("software-factory-runner:runner-v1", "software-factory-agent:agent-v2"),
        (RUNNER.split("@")[0] + ":runner-v1", AGENT.split("@")[0] + ":agent-v2"),
    ],
)
def test_explicit_start_uses_selected_images_and_private_mounts(tmp_path: Path, runner: str, agent: str) -> None:
    result, calls, home = launch(tmp_path, runner=runner, agent=agent)
    assert result.returncode == 0, result.stderr
    args = calls[-1]
    assert args[:3] == ["--host", "unix:///var/run/docker.sock", "run"]
    assert args[args.index("--user") + 1] == "2000:2000"
    assert args[args.index("--group-add") + 1] == "998"
    assert args[args.index("--pull=never") + 1 :][:2] == ["--platform", "linux/arm64"]
    assert args[-3:] == [RUNNER_ID, "--config", "/home/factory/.config/software-factory/factory.toml"]
    mounts = [args[i + 1] for i, value in enumerate(args) if value == "--mount"]
    assert "type=bind,src=/home/factory/artifacts,dst=/home/factory/artifacts" in mounts
    assert args[args.index("--env") + 1] == f"AGENT_IMAGE={agent}"
    assert len([call for call in calls if "run" in call]) == 1
    assert "--entrypoint" not in args
    assert (
        f"type=bind,src={home}/.config/software-factory,dst=/home/factory/.config/software-factory,readonly" in mounts
    )
    assert f"type=bind,src={home}/.pi/agent,dst=/home/factory/.pi/agent" in mounts
    assert "type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock" in mounts
    assert not any("pull" in call or "login" in call for call in calls)
    logs = list((home / ".local/state/software-factory").glob("start-*/runner.log"))
    assert len(logs) == 1
    assert logs[0].stat().st_mode & 0o777 == 0o600
    assert logs[0].parent.stat().st_mode & 0o777 == 0o700
    assert "runner_polling" in logs[0].read_text()
    assert "runner_polling" not in result.stdout + result.stderr
    assert (tmp_path / "notified").read_text() == "--ready\n"
    assert args[args.index("--cidfile") + 1] == str(tmp_path / "runtime/runner.cid")
    assert (home / ".config/software-factory/factory.toml").read_text() == "private configuration fixture"


@pytest.mark.parametrize(
    "failure",
    [
        "active",
        "native",
        "inspection",
        "platform",
        "image-id",
        "missing-runner",
        "missing-agent",
        "config",
        "startup",
        "notify",
    ],
)
def test_start_failure_is_not_retried_and_preserves_state(tmp_path: Path, failure: str) -> None:
    result, calls, home = launch(tmp_path, failure)
    assert result.returncode != 0
    assert calls or failure == "native"
    launches = [call for call in calls if "run" in call and "--entrypoint" not in call]
    assert len(launches) == (1 if failure in {"config", "startup", "notify"} else 0)
    assert (home / ".config/software-factory/deployment.env").read_text() == (
        f"RUNNER_IMAGE={RUNNER}\nAGENT_IMAGE={AGENT}\n"
    )
    assert "private configuration fixture" not in result.stdout + result.stderr
    assert not (tmp_path / "notified").exists()


@pytest.mark.parametrize("failure", ["missing-runner", "missing-agent"])
def test_missing_tagged_image_blocks_start(tmp_path: Path, failure: str) -> None:
    result, calls, _ = launch(tmp_path, failure, runner="runner:v1", agent="agent:v2")
    assert result.returncode != 0
    assert all("run" not in call for call in calls)


@pytest.mark.parametrize("image", ["--unsafe", "https://registry/image:tag", "bad image:tag"])
def test_start_rejects_unsafe_image_arguments(tmp_path: Path, image: str) -> None:
    result, calls, _ = launch(tmp_path, runner=image)
    assert result.returncode != 0
    assert not calls


def test_service_is_manual_only_and_allows_bounded_cleanup() -> None:
    unit = (ROOT / "infra/ec2/software-factory.service").read_text()
    assert "User=factory" in unit and "Group=factory" in unit
    assert "RequiresMountsFor=/home/factory /var/lib/docker /var/lib/containerd" in unit
    assert "Restart=no" in unit
    assert "[Install]" not in unit
    assert "ExecStart=/usr/local/sbin/factory-start-runner" in unit
    assert "Type=notify" in unit and "NotifyAccess=all" in unit
    assert "RuntimeDirectory=software-factory" in unit and "RuntimeDirectoryMode=0700" in unit
    assert "ExecStop=/usr/local/sbin/factory-stop-runner" in unit
    assert "ExecStopPost=/usr/local/sbin/factory-stop-runner" in unit
    assert "TimeoutStopSec=150" in unit
    assert "KillMode=process" in unit
    assert "SuccessExitStatus=130" in unit


@pytest.mark.parametrize("state", ["owned", "absent", "invalid", "stop-failed"])
def test_stop_only_targets_the_service_owned_container(tmp_path: Path, state: str) -> None:
    cid = tmp_path / "runner.cid"
    if state != "absent":
        cid.write_text(("--not-a-container" if state == "invalid" else "a" * 64) + "\n")
    retained = tmp_path / "previous-failure/run.log"
    retained.parent.mkdir()
    retained.write_text("private retained diagnostics")
    unrelated = tmp_path / "unrelated-container"
    unrelated.write_text("running")
    section = (ROOT / "docs/operations.md").read_text().split("## Stop for maintenance\n", 1)[1].split("\n## ", 1)[0]
    blocks = re.findall(r"```sh\n(.*?)```", section, re.DOTALL)
    assert len(blocks) == 1
    marker = tmp_path / "stopped"
    harness = """
sudo() {
  test "$*" = 'systemctl stop software-factory.service' || return 99
  bash "$STOPPER"
}
docker() { printf '%s\\n' "$*" >> "$MARKER"; test "$STATE" != stop-failed; }
export -f docker
"""
    command = ["bash", "-c", harness + blocks[0]]
    env = {
        **os.environ,
        "RUNTIME_DIRECTORY": str(tmp_path),
        "MARKER": str(marker),
        "STATE": state,
        "STOPPER": str(SCRIPTS / "stop-runner.sh"),
    }
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
    assert (result.returncode == 0) is (state in {"owned", "absent"})
    assert marker.exists() is (state in {"owned", "stop-failed"})
    if marker.exists():
        assert marker.read_text().strip() == "--host unix:///var/run/docker.sock stop --time 120 " + "a" * 64
    assert cid.exists() is (state in {"invalid", "stop-failed"})
    if result.returncode == 0:
        again = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
        assert again.returncode == 0
        assert not marker.exists() or len(marker.read_text().splitlines()) == 1
    assert retained.read_text() == "private retained diagnostics"
    assert unrelated.read_text() == "running"
