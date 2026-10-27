import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from tests_support import app_credentials

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
    test "$(stat -c %u:%g "$HOME")" = 2000:2000
    test "$XDG_CACHE_HOME" = "$HOME/.cache"
    test "$NPM_CONFIG_PREFIX" = "$HOME/.local"
    case "$PATH" in "$NPM_CONFIG_PREFIX/bin":*) ;; *) exit 1 ;; esac
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
    printf '\\nFACTORY_INSTRUCTIONS\\n'
    cat /opt/software-factory/pi/AGENTS.md
    printf '\\nFACTORY_SKILLS\\n'
    python - <<'PY'
import json
from pathlib import Path
root = Path('/opt/software-factory/pi/skills')
files = ('test-driven-development/SKILL.md', 'test-driven-development/testing-anti-patterns.md', 'ponytail/SKILL.md')
print(json.dumps({file: (root / file).read_text() for file in files}))
PY
    """
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
    instructions, _, skills = result.stdout.partition("\nFACTORY_INSTRUCTIONS\n")[2].partition("\nFACTORY_SKILLS\n")
    assert instructions == (ROOT / "agent/pi/AGENTS.md").read_text()
    root = ROOT / "agent/pi/skills"
    files = (
        "test-driven-development/SKILL.md",
        "test-driven-development/testing-anti-patterns.md",
        "ponytail/SKILL.md",
    )
    assert json.loads(skills) == {file: (root / file).read_text() for file in files}


def test_pinned_pi_loads_factory_and_target_context_without_project_trust() -> None:
    script = r"""
import assert from 'node:assert/strict';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { DefaultResourceLoader, SettingsManager } from
    '/usr/local/lib/node_modules/@earendil-works/pi-coding-agent/dist/index.js';
import { parseArgs } from '/usr/local/lib/node_modules/@earendil-works/pi-coding-agent/dist/cli/args.js';

const root = mkdtempSync('/tmp/factory-context-');
try {
    const agentDir = join(root, 'agent');
    const cwd = join(root, 'target');
    mkdirSync(agentDir);
    mkdirSync(join(cwd, '.pi'), { recursive: true });
    const baked = '/opt/software-factory/pi/AGENTS.md';
    const skillRoot = join(root, 'skills');
    for (const file of ['test-driven-development/SKILL.md', 'test-driven-development/testing-anti-patterns.md',
        'ponytail/SKILL.md']) {
        mkdirSync(join(skillRoot, file, '..'), { recursive: true });
        copyFileSync(join('/opt/software-factory/pi/skills', file), join(skillRoot, file));
    }
    const skillPaths = ['test-driven-development', 'ponytail'].map(name => join(skillRoot, name, 'SKILL.md'));
    const args = parseArgs(['--no-skills', ...skillPaths.flatMap(path => ['--skill', path])]);
    assert.deepEqual(args.skills, skillPaths);
    assert.equal(args.noSkills, true);
    const context = readFileSync(baked, 'utf8') + skillPaths.map(path =>
        `\n\n# Required factory skill\nSource: ${path}\nBase directory: ${join(path, '..')}\n\n`
        + readFileSync(path, 'utf8')).join('');
    writeFileSync(join(agentDir, 'AGENTS.md'), context);
    const reference = join(skillRoot, 'test-driven-development', 'testing-anti-patterns.md');
    assert.ok(readFileSync(reference, 'utf8').trim());
    for (const base of [join(cwd, '.pi', 'skills', 'ponytail'), join(cwd, '.agents', 'skills', 'extra'),
        join(agentDir, 'skills', 'extra')]) {
        mkdirSync(base, { recursive: true });
        const name = base.endsWith('ponytail') ? 'ponytail' : 'extra';
        writeFileSync(join(base, 'SKILL.md'), `---\nname: ${name}\ndescription: unapproved\n---\nunapproved`);
    }
    writeFileSync(join(cwd, 'AGENTS.md'), 'target instructions');
    writeFileSync(join(cwd, '.pi', 'settings.json'), JSON.stringify({ defaultModel: 'untrusted-model' }));
    writeFileSync(join(cwd, '.pi', 'SYSTEM.md'), 'untrusted system prompt');
    writeFileSync(join(cwd, '.pi', 'APPEND_SYSTEM.md'), 'untrusted appended prompt');
    const settingsManager = SettingsManager.create(cwd, agentDir, { projectTrusted: false });
    const loader = new DefaultResourceLoader({ cwd, agentDir, settingsManager,
        noExtensions: true, noSkills: args.noSkills, additionalSkillPaths: args.skills,
        noPromptTemplates: true, noThemes: true });
    await loader.reload();
    const factory = { path: join(agentDir, 'AGENTS.md'), content: context };
    assert.deepEqual(loader.getAgentsFiles().agentsFiles, [factory,
        { path: join(cwd, 'AGENTS.md'), content: 'target instructions' }]);
    assert.equal(settingsManager.getDefaultModel(), undefined);
    assert.equal(loader.getSystemPrompt(), undefined);
    assert.deepEqual(loader.getAppendSystemPrompt(), []);
    assert.deepEqual(loader.getExtensions().extensions, []);
    assert.deepEqual(loader.getSkills().diagnostics, []);
    assert.deepEqual(loader.getSkills().skills.map(skill => skill.filePath), skillPaths);
    assert.deepEqual(loader.getSkills().skills.map(skill => skill.name), ['test-driven-development', 'ponytail']);
    assert.deepEqual(loader.getPrompts().prompts, []);
    writeFileSync(join(cwd, 'AGENTS.override.md'), 'target override');
    await loader.reload();
    assert.deepEqual(loader.getAgentsFiles().agentsFiles, [factory,
        { path: join(cwd, 'AGENTS.override.md'), content: 'target override' }]);
    assert.deepEqual(loader.getSkills().skills.map(skill => skill.filePath), skillPaths);
    for (const path of skillPaths) {
        const [opening, frontmatter, ...body] = readFileSync(path, 'utf8').split('---');
        writeFileSync(path, opening + '---' + '\n' + frontmatter.trim().split('\n').reverse().join('\n')
            + '\n---' + body.join('---'));
    }
    writeFileSync(join(skillRoot, 'README.md'), 'Extra bundle documentation');
    writeFileSync(join(skillRoot, 'ponytail', 'README.md'), 'Extra skill documentation');
    await loader.reload();
    assert.deepEqual(loader.getSkills().diagnostics, []);
    assert.deepEqual(loader.getSkills().skills.map(skill => skill.filePath), skillPaths);
    for (const defect of ['missing', 'invalid']) {
        if (defect === 'missing') rmSync(skillPaths[0]);
        else writeFileSync(skillPaths[0], '---\nname: [invalid\n---\nBroken skill');
        await loader.reload();
        assert.ok(loader.getSkills().diagnostics.length > 0);
        assert.deepEqual(loader.getSkills().skills.map(skill => skill.filePath), [skillPaths[1]]);
    }
} finally {
    rmSync(root, { recursive: true, force: true });
}
"""
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--interactive",
            "--pull=never",
            "--platform",
            "linux/arm64",
            "--network",
            "none",
            "--env",
            "PI_OFFLINE=1",
            "--env",
            "PI_TELEMETRY=0",
            "--entrypoint",
            "node",
            IMAGE,
            "--input-type=module",
        ],
        input=script,
        capture_output=True,
        text=True,
        check=True,
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


@pytest.mark.parametrize("tool", [None, "npm", "bash", "git", "make", "cc", "c++", "curl", "tar", "unzip", "sudo"])
def test_startup_checks_tool_capabilities_and_removes_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool: str | None
) -> None:
    calls = []
    monkeypatch.setattr("software_factory.runner.GitHubApp.load", Mock(return_value=Mock()))

    class ScriptedAuthentication(Commands):
        def run(self, args, phase, **kwargs):
            calls.append((args, phase))
            if phase == "GitHub authentication":
                return json.dumps({"full_name": "owner/repo"})
            if phase == "Copilot authentication":
                return f"proxy-ep=proxy.business.githubcopilot.com;exp={int(time.time()) + 1800}"
            if phase == "agent runtime":
                fixture = (
                    f"printf '#!/bin/sh\\necho broken-tool-invoked:{tool} >&2\\nexit 42\\n' "
                    f'> "$NPM_CONFIG_PREFIX/bin/{tool}"\n'
                    f'chmod 755 "$NPM_CONFIG_PREFIX/bin/{tool}"\n'
                    if tool
                    else 'export PATH="/tmp/extra-path:$PATH"\n'
                )
                args = [*args[:-1], fixture + args[-1]]
                self.log = tmp_path / "runtime.log"
            return super().run(args, phase, **kwargs)

    monkeypatch.setattr("software_factory.runner.Commands", ScriptedAuthentication)
    monkeypatch.setattr("software_factory.runner.shutil.which", lambda name: "/bin/" + name)
    config = Config("owner/repo", "chosen", IMAGE, tmp_path / "artifacts")
    if tool:
        with pytest.raises(FactoryError, match="agent runtime check failed"):
            preflight(config)
    else:
        preflight(config)
    runtime = next(args for args, phase in calls if phase == "startup agent")
    name = runtime[runtime.index("--name") + 1]
    assert calls[-1] == (["docker", "rm", "--force", "--volumes", name], "startup cleanup")
    containers = subprocess.check_output(["docker", "ps", "-aq", "--filter", f"name=^{name}$"], text=True)
    assert not containers.strip(), "startup probe left a container behind"
    assert list(config.artifacts_dir.iterdir()) == []
    if tool:
        assert f"broken-tool-invoked:{tool}" in (tmp_path / "runtime.log").read_text()


@pytest.mark.parametrize(
    "defect",
    [
        "root",
        "wrong-uid",
        "wrong-gid",
        "home",
        "cache",
        "prefix",
        "bin",
        "unreadable-home",
        "unreadable-cache",
        "unreadable-prefix",
        "unreadable-bin",
        "missing-cache",
        "missing-bin",
        "unsearchable-home",
        "unsearchable-cache",
        "unsearchable-prefix",
        "unsearchable-bin",
        "missing-instructions",
        "unreadable-instructions",
        "empty-instructions",
        "whitespace-instructions",
        *[
            f"{defect}:{file}"
            for file in (
                "test-driven-development/SKILL.md",
                "test-driven-development/testing-anti-patterns.md",
                "ponytail/SKILL.md",
            )
            for defect in ("missing", "unreadable", "empty", "whitespace")
        ],
    ],
)
def test_startup_rejects_incompatible_image_without_runtime_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defect: str
) -> None:
    names = []
    monkeypatch.setattr("software_factory.runner.GitHubApp.load", Mock(return_value=Mock()))

    class IncompatibleImage(Commands):
        def run(self, args, phase, **kwargs):
            if phase == "GitHub authentication":
                return json.dumps({"full_name": "owner/repo"})
            if phase == "Copilot authentication":
                return f"proxy-ep=proxy.business.githubcopilot.com;exp={int(time.time()) + 1800}"
            if phase == "startup agent":
                names.append(args[args.index("--name") + 1])
                if defect in {"root", "wrong-uid", "wrong-gid"}:
                    user = {"root": "0:0", "wrong-uid": "2001:2000", "wrong-gid": "2000:2001"}[defect]
                    args = [*args[:2], "--user", user, *args[2:]]
            if phase == "agent runtime" and defect not in {"root", "wrong-uid", "wrong-gid"}:
                if ":" in defect:
                    mode, file = defect.split(":", 1)
                    path = "/opt/software-factory/pi/skills/" + file
                    mutation = {
                        "missing": f"rm {path}",
                        "unreadable": f"chmod 000 {path}",
                        "empty": f": > {path}",
                        "whitespace": f"printf ' \\n\\t' > {path}",
                    }[mode]
                else:
                    mutation = {
                        "home": "chmod 0555 /tmp/factory-home",
                        "cache": "chmod 0555 /tmp/factory-home/.cache",
                        "prefix": "chmod 0555 /tmp/factory-home/.local",
                        "bin": "chmod 0555 /tmp/factory-home/.local/bin",
                        "unreadable-home": "chmod 0300 /tmp/factory-home",
                        "unreadable-cache": "chmod 0300 /tmp/factory-home/.cache",
                        "unreadable-prefix": "chmod 0300 /tmp/factory-home/.local",
                        "unreadable-bin": "chmod 0300 /tmp/factory-home/.local/bin",
                        "missing-cache": "rmdir /tmp/factory-home/.cache",
                        "missing-bin": "rmdir /tmp/factory-home/.local/bin",
                        "unsearchable-home": "chmod 0600 /tmp/factory-home",
                        "unsearchable-cache": "chmod 0600 /tmp/factory-home/.cache",
                        "unsearchable-prefix": "chmod 0600 /tmp/factory-home/.local",
                        "unsearchable-bin": "chmod 0600 /tmp/factory-home/.local/bin",
                        "missing-instructions": "rm /opt/software-factory/pi/AGENTS.md",
                        "unreadable-instructions": "chmod 000 /opt/software-factory/pi/AGENTS.md",
                        "empty-instructions": ": > /opt/software-factory/pi/AGENTS.md",
                        "whitespace-instructions": "printf ' \\n\\t' > /opt/software-factory/pi/AGENTS.md",
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
    home = tmp_path / "home"
    tools = tmp_path / "tools"
    tools.mkdir()
    app_credentials(home, tools)
    marker = tmp_path / "github-calls"
    gh = tools / "gh"
    gh.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        f"path = pathlib.Path({str(marker)!r})\n"
        "with path.open('a') as log: log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "assert os.environ['GH_TOKEN'] == 'fixture-installation-token'\n"
        "if 'repos/owner/repo' in sys.argv:\n"
        "    print(json.dumps({'full_name':'owner/repo'}))\n"
        "else:\n"
        "    assert any('issues?state=open&labels=' in arg for arg in sys.argv)\n"
        "    print(json.dumps([[]]))\n"
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
            env={
                **os.environ,
                "HOME": str(home),
                "DOCKER_CONFIG": os.environ.get("DOCKER_CONFIG", str(Path.home() / ".docker")),
                "PATH": str(tools) + os.pathsep + os.environ["PATH"],
            },
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
    assert all("--method" not in call or call[call.index("--method") + 1] == "GET" for call in calls)
    containers = subprocess.check_output(
        ["docker", "ps", "-aq", "--filter", "name=factory-startup-", "--filter", f"ancestor={image_id}"], text=True
    )
    assert not containers.strip(), "startup probe left a container behind"
