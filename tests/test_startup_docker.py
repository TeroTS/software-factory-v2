import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from software_factory.config import Config
from software_factory.process import Commands, FactoryError
from software_factory.runner import preflight

ROOT = Path(__file__).resolve().parents[1]
IMAGE = os.environ.get("FACTORY_AGENT_IMAGE", "software-factory-agent:1.0.0")
pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        os.environ.get("FACTORY_AGENT_IMAGE_TESTS") != "1",
        reason="build the shared ARM64 image and set FACTORY_AGENT_IMAGE_TESTS=1",
    ),
]


def test_shared_image_has_pinned_native_baseline_and_no_credentials() -> None:
    inspected = json.loads(subprocess.check_output(["docker", "image", "inspect", IMAGE], text=True))[0]
    assert inspected["Os"] == "linux" and inspected["Architecture"] == "arm64"
    assert inspected["Config"]["User"] == "factory:factory"
    assert not inspected["Config"].get("Volumes")
    assert not any(variable.startswith("UV_PYTHON_DOWNLOADS=") for variable in inspected["Config"]["Env"])
    assert not any(
        key in variable.split("=", 1)[0].upper()
        for variable in inspected["Config"]["Env"]
        for key in ("TOKEN", "SECRET", "CREDENTIAL", "PASSWORD")
    )
    script = """set -eu
    test "$(uname -m)" = aarch64
    test "$(id -u):$(id -g):$(id -un):$(id -gn)" = 2000:2000:factory:factory
    test "$(getent passwd factory | cut -d: -f3-4)" = 2000:2000
    test "$(getent group factory | cut -d: -f3)" = 2000
    test "$HOME" = /tmp/factory-home
    touch "$HOME/home-write" "$XDG_CACHE_HOME/cache-write"
    touch "$NPM_CONFIG_PREFIX/prefix-write" "$NPM_CONFIG_PREFIX/bin/tool-write"
    sudo -n sh -ec 'test "$(id -u)" = 0; test "$HOME" = /root'
    printf '%s\\n' 'Defaults:factory always_set_home' 'factory ALL=(root) NOPASSWD: ALL' > /tmp/expected-sudo
    sudo -n cmp /etc/sudoers.d/factory /tmp/expected-sudo
    test "$(node --version)" = v22.19.0
    test "$(npm --version)" = 10.9.3
    test "$(python --version)" = 'Python 3.14.3'
    test "$(uv --version)" = 'uv 0.5.13'
    test "$(pi --version)" = 1.3.0
    docker --version | grep '28.4.0'
    docker compose version | grep 'v2.39.4'
    sudo --version >/dev/null
    for tool in bash git make cc c++ curl tar; do "$tool" --version >/dev/null; done
    unzip -v >/dev/null
    test -s /etc/ssl/certs/ca-certificates.crt
    test ! -e /root/.pi/agent/auth.json
    test ! -e /root/.config/gh/hosts.yml
    """
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--platform",
            "linux/arm64",
            "--network",
            "none",
            "--entrypoint",
            "sh",
            inspected["Id"],
            "-ec",
            script,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_image_does_not_grant_sudo_to_other_accounts() -> None:
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--platform",
            "linux/arm64",
            "--network",
            "none",
            "--user",
            "65534:65534",
            "--entrypoint",
            "sudo",
            IMAGE,
            "-n",
            "true",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert "sudo" in result.stderr


@pytest.mark.parametrize("tool", ["npm", "bash", "git", "make", "cc", "c++", "curl", "tar", "unzip", "sudo"])
def test_startup_rejects_broken_required_tool_and_removes_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool: str
) -> None:
    calls = []

    class ScriptedAuthentication(Commands):
        def run(self, args, phase, **kwargs):
            calls.append((args, phase))
            if phase == "GitHub authentication":
                return ""
            if phase == "Copilot authentication":
                return f"proxy-ep=proxy.business.githubcopilot.com;exp={int(time.time()) + 1800}"
            if phase == "agent runtime":
                fixture = (
                    "mkdir /tmp/broken-bin\n"
                    f"printf '#!/bin/sh\\nexit 42\\n' > /tmp/broken-bin/{tool}\n"
                    f"chmod 755 /tmp/broken-bin/{tool}\n"
                    "export PATH=/tmp/broken-bin:$PATH\n"
                )
                args = [*args[:-1], fixture + args[-1]]
            return super().run(args, phase, **kwargs)

    monkeypatch.setattr("software_factory.runner.Commands", ScriptedAuthentication)
    monkeypatch.setattr("software_factory.runner.shutil.which", lambda name: "/bin/" + name)
    config = Config("owner/repo", "chosen", IMAGE, tmp_path / "artifacts")
    with pytest.raises(FactoryError, match="agent runtime check failed"):
        preflight(config)
    runtime = next(args for args, phase in calls if phase == "startup agent")
    name = runtime[runtime.index("--name") + 1]
    assert calls[-1] == (["docker", "rm", "--force", "--volumes", name], "startup cleanup")
    containers = subprocess.check_output(["docker", "ps", "-aq", "--filter", f"name=^{name}$"], text=True)
    assert not containers.strip(), "failed startup probe left a container behind"
    assert list(config.artifacts_dir.iterdir()) == []


@pytest.mark.parametrize(
    "defect",
    ["root", "wrong-uid", "wrong-gid", "home", "cache", "prefix", "bin", "account", "missing-cache", "missing-bin"],
)
def test_startup_rejects_incompatible_identity_or_home_without_runtime_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str
) -> None:
    names = []

    class IncompatibleImage(Commands):
        def run(self, args, phase, **kwargs):
            if phase == "GitHub authentication":
                return ""
            if phase == "Copilot authentication":
                return f"proxy-ep=proxy.business.githubcopilot.com;exp={int(time.time()) + 1800}"
            if phase == "startup agent":
                names.append(args[args.index("--name") + 1])
                if defect in {"root", "wrong-uid", "wrong-gid"}:
                    user = {"root": "0:0", "wrong-uid": "2001:2000", "wrong-gid": "2000:2001"}[defect]
                    args = [*args[:2], "--user", user, *args[2:]]
            if phase == "agent runtime" and defect not in {"root", "wrong-uid", "wrong-gid"}:
                mutation = {
                    "home": "chmod 0555 /tmp/factory-home",
                    "cache": "chmod 0555 /tmp/factory-home/.cache",
                    "prefix": "chmod 0555 /tmp/factory-home/.local",
                    "bin": "chmod 0555 /tmp/factory-home/.local/bin",
                    "account": "sed -i 's/^factory:/old-factory:/' /etc/passwd",
                    "missing-cache": "rmdir /tmp/factory-home/.cache",
                    "missing-bin": "rmdir /tmp/factory-home/.local/bin",
                }[defect]
                super().run(
                    ["docker", "exec", "--user", "0:0", names[0], "sh", "-ec", mutation],
                    "break fixture image",
                    env=kwargs["env"],
                )
            assert phase != "agent user configuration", "startup must not repair incompatible images"
            return super().run(args, phase, **kwargs)

    monkeypatch.setattr("software_factory.runner.Commands", IncompatibleImage)
    monkeypatch.setattr("software_factory.runner.shutil.which", lambda name: "/bin/" + name)
    with pytest.raises(FactoryError, match="rebuild.*restart"):
        preflight(Config("owner/repo", "chosen", IMAGE, tmp_path / "artifacts"))
    assert len(names) == 1
    remaining = subprocess.check_output(["docker", "ps", "-aq", "--filter", f"name=^{names[0]}$"], text=True)
    assert not remaining.strip()


def test_operator_starts_real_cli_with_shared_image_and_observes_idle_polling(tmp_path: Path) -> None:
    tools = tmp_path / "tools"
    tools.mkdir()
    marker = tmp_path / "github-calls"
    gh = tools / "gh"
    gh.write_text(
        f"#!{sys.executable}\n"
        "import json, pathlib, sys\n"
        f"path = pathlib.Path({str(marker)!r})\n"
        "with path.open('a') as log: log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if sys.argv[1:3] == ['auth', 'status']: sys.exit(0)\n"
        "assert '--method' in sys.argv and sys.argv[sys.argv.index('--method') + 1] == 'GET'\n"
        "assert any('issues?state=open&labels=' in arg for arg in sys.argv)\n"
        "print(json.dumps([[]]))\n"
    )
    gh.chmod(0o755)
    pi = tools / "pi"
    pi.write_text(
        "#!/bin/sh\n[ \"$1 $2 $3\" = 'auth print-bearer-token --provider' ] || exit 99\n"
        f"printf '%s\\n' 'proxy-ep=proxy.business.githubcopilot.com;exp={int(time.time()) + 1800}'\n"
    )
    pi.chmod(0o755)
    config = tmp_path / "factory.toml"
    config.write_text(f'repository = "owner/repo"\nmodel = "chosen"\nagent_image = "{IMAGE}"\nartifacts_dir = "runs"\n')
    previous = tmp_path / "runs" / "issue-17-failed"
    previous.mkdir(parents=True)
    (previous / "run.log").write_text("previous diagnostic\n")
    image_id = subprocess.check_output(["docker", "image", "inspect", IMAGE, "--format", "{{.Id}}"], text=True).strip()
    output = tmp_path / "stderr"
    with output.open("w") as stderr:
        process = subprocess.Popen(
            [sys.executable, "-m", "software_factory", "--config", str(config)],
            cwd=ROOT,
            env={**os.environ, "PATH": str(tools) + os.pathsep + os.environ["PATH"]},
            stdout=subprocess.DEVNULL,
            stderr=stderr,
        )
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                text = output.read_text()
                if "first-pass execution active" in text and marker.exists():
                    calls = [json.loads(line) for line in marker.read_text().splitlines()]
                    if any(call[0] == "api" for call in calls):
                        break
                assert process.poll() is None, text
                time.sleep(0.1)
            else:
                pytest.fail("CLI did not reach polling: " + output.read_text())
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
            process.wait(timeout=15)
    assert process.returncode == 130
    assert "Polling owner/repo every 30 seconds" in output.read_text()
    assert "Traceback" not in output.read_text()
    assert list(previous.parent.iterdir()) == [previous]
    assert (previous / "run.log").read_text() == "previous diagnostic\n"
    calls = [json.loads(line) for line in marker.read_text().splitlines()]
    assert all(call[:2] == ["auth", "status"] or call[call.index("--method") + 1] == "GET" for call in calls)
    containers = subprocess.check_output(
        ["docker", "ps", "-aq", "--filter", "name=factory-startup-", "--filter", f"ancestor={image_id}"], text=True
    )
    assert not containers.strip(), "startup probe left a container behind"
