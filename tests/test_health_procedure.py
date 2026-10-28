import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SECTION = (ROOT / "docs/operations.md").read_text().split("## Operational health\n", 1)[1].split("\n## ", 1)[0]
BLOCKS = re.findall(r"```bash\n(.*?)```", SECTION, re.DOTALL)
RUNNER = "registry/software-factory-runner@sha256:" + "a" * 64
AGENT = "registry/software-factory-agent@sha256:" + "b" * 64


@pytest.mark.parametrize(
    "state,events,expected_status",
    [
        ("running", ["runner_polling", "poll_started"], [0, 0, 0]),
        ("stopped", ["runner_polling", "runner_interrupted"], [0, 1, 1]),
        ("failed", ["runner_failed"], [0, 1, 1]),
        ("running", ["runner_polling", "poll_failed"], [0, 0, 0]),
        ("running", ["runner_polling", "run_started", "phase_started", "cleanup_failed"], [0, 0, 0]),
        ("missing-log", [], [0, 0, 2]),
        ("denied-service", ["runner_polling", "poll_started"], [1, 0, 0]),
        ("denied-docker", ["runner_polling", "poll_started"], [0, 1, 0]),
        ("missing-selection", ["runner_polling", "poll_started"], [0, 2, 0]),
    ],
)
def test_documented_health_checks_only_read_existing_evidence(
    tmp_path: Path, state: str, events: list[str], expected_status: list[int]
) -> None:
    assert len(BLOCKS) == 3
    home = tmp_path / "home"
    config = home / ".config/software-factory"
    config.mkdir(parents=True)
    selection = config / "deployment.env"
    if state != "missing-selection":
        selection.write_text(f"RUNNER_IMAGE={RUNNER}\nAGENT_IMAGE={AGENT}\n")
    (config / "github-app.pem").write_text("PRIVATE KEY MUST NOT APPEAR")
    log = home / ".local/state/software-factory/start-fixture/runner.log"
    log.parent.mkdir(parents=True)
    if state != "missing-log":
        log.write_text(
            "\n".join(json.dumps({"event": event, "timestamp": "2026-07-24T12:00:00Z"}) for event in events)
            + "\nRAW TRANSCRIPT MUST NOT APPEAR\n"
        )
    calls = tmp_path / "calls.jsonl"
    stub = tmp_path / "boundary.py"
    stub.write_text("""import json, os, sys
args = sys.argv[1:]
with open(os.environ["CALLS"], "a") as output:
    output.write(json.dumps(args) + "\\n")
state = os.environ["STATE"]
if args == ["systemctl", "show", "software-factory.service",
            "--property=ActiveState,SubState,Result,ExecMainStatus,ExecMainStartTimestamp"]:
    if state == "denied-service": sys.exit(1)
    print({"stopped": "ActiveState=inactive\\nSubState=dead\\nResult=success",
           "failed": "ActiveState=failed\\nSubState=failed\\nResult=exit-code"}.get(
               state, "ActiveState=active\\nSubState=running\\nResult=success"))
elif args == ["journalctl", "-u", "software-factory.service", "--no-pager", "-n", "30"]:
    if state == "denied-service": sys.exit(1)
    print("Private startup/progress log: " + os.environ["LOG"])
elif args == ["docker", "--host", "unix:///var/run/docker.sock", "container", "inspect", "--format",
              "runner={{.Config.Image}} image_id={{.Image}} status={{.State.Status}}", "software-factory"]:
    if state in {"stopped", "failed", "denied-docker"}: sys.exit(1)
    print("runner=" + os.environ["RUNNER"] + " image_id=sha256:fixture status=running")
else:
    sys.exit("Unexpected or mutating boundary call: " + repr(args))
""")
    harness = """
sudo() { python3 "$STUB" "$@"; }
docker() { python3 "$STUB" docker "$@"; }
export -f sudo docker
"""
    before = {path: path.read_bytes() for path in home.rglob("*") if path.is_file()}
    results = [
        subprocess.run(
            ["bash", "-c", harness + block],
            env={
                **os.environ,
                "HOME": str(home),
                "LOG": str(log),
                "STUB": str(stub),
                "CALLS": str(calls),
                "STATE": state,
                "RUNNER": RUNNER,
            },
            text=True,
            capture_output=True,
            timeout=10,
        )
        for block in BLOCKS
    ]
    assert [result.returncode for result in results] == expected_status
    assert {path: path.read_bytes() for path in home.rglob("*") if path.is_file()} == before
    output = "".join(result.stdout + result.stderr for result in results)
    assert "PRIVATE KEY MUST NOT APPEAR" not in output
    assert "RAW TRANSCRIPT MUST NOT APPEAR" not in output
    if state != "missing-selection":
        assert RUNNER in output and AGENT in output
    if state != "missing-log":
        for event in events:
            assert f'"event": "{event}"' in output
    assert all(json.loads(line)[0] in {"systemctl", "journalctl", "docker"} for line in calls.read_text().splitlines())
