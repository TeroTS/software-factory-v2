import io
import os
import shutil
import subprocess
import tarfile
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    os.environ.get("FACTORY_PROVISION_TESTS") != "1" or shutil.which("limactl") is None,
    reason="set FACTORY_PROVISION_TESTS=1 to explicitly provision the existing authorized Lima factory VM",
)


def test_operator_provisions_checks_and_repeats_without_erasing_state():
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as stream:
        for name in (
            "scripts/provision-host",
            "src/software_factory/__init__.py",
            "src/software_factory/process.py",
            "src/software_factory/provision.py",
        ):
            stream.add(ROOT / name, arcname=name)
    stage = subprocess.check_output(
        ["limactl", "shell", "factory", "sudo", "-n", "mktemp", "-d", "/var/tmp/factory-bootstrap.XXXXXXXX"],
        text=True,
        timeout=30,
    ).strip()
    assert stage.startswith("/var/tmp/factory-bootstrap.")
    subprocess.run(
        ["limactl", "shell", "factory", "sudo", "-n", "tar", "--no-same-owner", "-xf", "-", "-C", stage],
        input=archive.getvalue(),
        check=True,
        timeout=30,
    )
    command = ["limactl", "shell", "factory", "sudo", "-n", f"{stage}/scripts/provision-host"]
    for attempt in range(2):
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=3700)
        assert result.returncode == 0, f"Provisioning attempt {attempt + 1}: {result.stdout}\n{result.stderr}"
        assert "Factory host ready (2000:2000, native local Docker)" in result.stdout
        if attempt == 0:
            sentinel = f".factory-provision-check-{uuid.uuid4().hex}"
            subprocess.run(
                [
                    "limactl",
                    "shell",
                    "factory",
                    "sudo",
                    "-n",
                    "runuser",
                    "-u",
                    "factory",
                    "--",
                    "/usr/bin/python3",
                    "-I",
                    "-c",
                    "import pathlib,sys; p=pathlib.Path.home()/sys.argv[1]; p.mkdir(mode=0o700); "
                    "(p/'repository').write_text('preserve source'); "
                    "(p/'diagnostics').write_text('preserve diagnostics')",
                    sentinel,
                ],
                check=True,
                timeout=30,
            )
    result = subprocess.run(command + ["--check"], capture_output=True, text=True, check=False, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "Factory host ready" in result.stdout
    subprocess.run(
        [
            "limactl",
            "shell",
            "factory",
            "sudo",
            "-n",
            "runuser",
            "-u",
            "factory",
            "--",
            "/usr/bin/python3",
            "-I",
            "-c",
            "import pathlib,sys; p=pathlib.Path.home()/sys.argv[1]; "
            "assert p.stat().st_uid==2000 and p.stat().st_mode & 0o777 == 0o700; "
            "assert (p/'repository').read_text()=='preserve source'; "
            "assert (p/'diagnostics').read_text()=='preserve diagnostics'; "
            "(p/'repository').unlink(); (p/'diagnostics').unlink(); p.rmdir()",
            sentinel,
        ],
        check=True,
        timeout=30,
    )
