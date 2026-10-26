import io
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from software_factory.sandbox import PI_FLAGS

ROOT = Path(__file__).resolve().parents[1]
INSTRUCTIONS = Path("/opt/software-factory/pi/AGENTS.md")
SKILLS = Path("/opt/software-factory/pi/skills")
SKILL_NAMES = ("test-driven-development", "ponytail")
SKILL_FILES = (
    "test-driven-development/SKILL.md",
    "test-driven-development/testing-anti-patterns.md",
    "test-driven-development/LICENSE",
    "ponytail/SKILL.md",
    "ponytail/LICENSE",
)


@pytest.mark.parametrize("execution", ["script", "in-process"])
@pytest.mark.parametrize(
    "outcome",
    [
        "success",
        "updated-skills",
        "repair",
        "missing-instructions",
        "unreadable-instructions",
        "empty-instructions",
        "whitespace-instructions",
        "missing-model",
        "wrong-provider",
        "empty-catalog",
        "catalog-failure",
        "catalog-terminated",
        "execution-failure",
        "terminated",
        "missing-pi",
        "missing-execution",
        *[f"{defect}:{file}" for file in SKILL_FILES for defect in ("missing", "unreadable", "empty", "whitespace")],
    ],
)
def test_agent_wrapper_uses_ephemeral_credentials_and_exact_model(
    tmp_path: Path, outcome: str, execution: str, monkeypatch, capfd
) -> None:
    wrapper = ROOT / "src/software_factory/sandbox_agent.py"
    instructions = tmp_path / "baked-AGENTS.md"
    if outcome != "missing-instructions":
        instructions.write_text(
            {"empty-instructions": "", "whitespace-instructions": " \n"}.get(outcome, "factory rules\n")
        )
    if outcome == "unreadable-instructions":
        instructions.unlink()
        instructions.mkdir()  # A real read failure, independent of the test account's privileges.
    skills = tmp_path / "skills"
    for file in SKILL_FILES:
        path = skills / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"---\nname: {path.parent.name}\ndescription: fixture\n---\n\n{file} rules\n")
    if outcome == "updated-skills":
        for file in SKILL_FILES:
            path = skills / file
            path.write_text(path.read_text() + "Updated source content without a checksum manifest.\n")
    if ":" in outcome:
        defect, file = outcome.split(":", 1)
        path = skills / file
        if defect in {"missing", "unreadable"}:
            path.unlink()
            if defect == "unreadable":
                path.mkdir()
        else:
            path.write_text({"empty": "", "whitespace": " \n\t"}[defect])
    skill_paths = [str((skills if execution == "script" else SKILLS) / name / "SKILL.md") for name in SKILL_NAMES]
    pi = tmp_path / "pi"
    pi.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, signal, stat, sys\n"
        "home = pathlib.Path(os.environ['PI_CODING_AGENT_DIR'])\n"
        f"pathlib.Path({str(tmp_path / 'home-record')!r}).write_text(str(home))\n"
        "assert stat.S_IMODE(home.stat().st_mode) == 0o700\n"
        "assert stat.S_IMODE((home/'auth.json').stat().st_mode) == 0o600\n"
        "assert '--no-context-files' not in sys.argv\n"
        "assert (home/'AGENTS.md').read_text().startswith('factory rules\\n')\n"
        "assert 'private-bearer' not in ' '.join(sys.argv)\n"
        "assert os.environ['PI_OFFLINE'] == '1'\n"
        "assert os.environ['PI_TELEMETRY'] == '0'\n"
        "if '--list-models' in sys.argv:\n"
        f"    if {outcome == 'catalog-terminated'}: os.kill(os.getpid(), signal.SIGTERM)\n"
        f"    if {outcome == 'missing-execution'}: pathlib.Path(sys.argv[0]).unlink()\n"
        f"    print('{'other-provider' if outcome == 'wrong-provider' else 'github-copilot'} "
        f"{'chosen-extra' if outcome == 'missing-model' else 'chosen'} 128k 4k' "
        f"if {outcome != 'empty-catalog'} else '')\n"
        f"    sys.exit({7 if outcome == 'catalog-failure' else 0})\n"
        "else:\n"
        f"    assert [sys.argv[i+1] for i, arg in enumerate(sys.argv) if arg == '--skill'] == {skill_paths!r}\n"
        "    assert '--no-skills' in sys.argv\n"
        f"    for path in {skill_paths!r}:\n"
        "        assert path in (home/'AGENTS.md').read_text()\n"
        "    print(json.dumps({'args': sys.argv[1:], 'auth': json.loads((home/'auth.json').read_text()), "
        "'models': json.loads((home/'models.json').read_text()), 'prompt': sys.stdin.read(), "
        "'home': str(home), 'instructions': (home/'AGENTS.md').read_text()}), flush=True)\n"
        f"    if {outcome == 'execution-failure'}: sys.exit(8)\n"
        f"    if {outcome == 'terminated'}: os.kill(os.getpid(), signal.SIGTERM)\n"
    )
    pi.chmod(0o755)
    if outcome == "missing-pi":
        pi.unlink()
    payload = {
        "snapshot": {"number": 7, "title": "task", "body": None},
        "bearer": "private-bearer",
        "endpoint": "https://api.business.githubcopilot.com",
        "model": "chosen",
        "flags": PI_FLAGS,
    }
    if outcome == "repair":
        payload["verification_output"] = "assert actual == expected\nverification stderr"
    # Execute real child processes in both modes; runpy also measures the standalone wrapper's Python coverage.
    if execution == "script":
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                wrapper.read_text().replace(str(INSTRUCTIONS), str(instructions)).replace(str(SKILLS), str(skills)),
            ],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            env={**os.environ, "PATH": str(tmp_path), "TMPDIR": str(tmp_path)},
        )
    else:
        read_text = Path.read_text

        def redirected(path):
            if path == INSTRUCTIONS:
                return instructions
            return skills / path.relative_to(SKILLS) if path.is_relative_to(SKILLS) else path

        monkeypatch.setattr(Path, "read_text", lambda path, *a, **kw: read_text(redirected(path), *a, **kw))
        monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
        with pytest.raises(SystemExit) as exit_status:
            runpy.run_path(str(wrapper), run_name="__main__")
        output = capfd.readouterr()
        result = SimpleNamespace(returncode=exit_status.value.code, stdout=output.out, stderr=output.err)
    record = tmp_path / "home-record"
    if record.exists():
        assert not Path(record.read_text()).exists()
    assert "private-bearer" not in result.stderr
    assert not list(tmp_path.glob("factory-pi-*"))
    if ":" in outcome:
        assert result.returncode == 1
        assert "factory Pi skills unavailable or incompatible; rebuild the shared image, then restart" in result.stderr
        assert "Traceback" not in result.stderr
        assert not record.exists(), "Pi must not run with unavailable or empty required skills"
        return
    if outcome.endswith("-instructions"):
        assert result.returncode == 1
        assert "factory Pi instructions unavailable; rebuild the shared image, then restart" in result.stderr
        assert "Traceback" not in result.stderr
        assert not record.exists(), "Pi must not run without factory instructions"
        return
    if outcome in {"missing-pi", "missing-execution"}:
        assert result.returncode == 1
        assert "Pi invocation failed" in result.stderr
        assert "Traceback" not in result.stderr
        return
    if outcome in {"missing-model", "wrong-provider", "empty-catalog", "catalog-failure", "catalog-terminated"}:
        assert result.returncode != 0
        assert "configured Copilot model is unavailable" in result.stderr
        assert "private-bearer" not in result.stderr
        return
    expected = {"success": 0, "updated-skills": 0, "repair": 0, "execution-failure": 8, "terminated": 1}
    assert result.returncode == expected[outcome], result.stderr
    output = json.loads(result.stdout)
    assert not Path(output["home"]).exists()
    assert output["auth"] == {"github-copilot": {"type": "api_key", "key": "private-bearer"}}
    assert output["models"]["providers"]["github-copilot"]["baseUrl"] == payload["endpoint"]
    assert "private-bearer" not in output["prompt"]
    assert output["instructions"].startswith("factory rules\n")
    for name, skill_path in zip(SKILL_NAMES, skill_paths, strict=True):
        assert output["instructions"].count((skills / name / "SKILL.md").read_text()) == 1
        assert skill_path in output["instructions"]
        assert f"{name}/SKILL.md rules" not in output["prompt"]
    assert "factory rules" not in output["prompt"]
    assert "COMPOSE_PROJECT_NAME" not in output["prompt"]
    assert "Do not publish, commit, or push" not in output["prompt"]
    if outcome == "repair":
        assert "Repair" in output["prompt"]
        assert payload["verification_output"] in output["prompt"]
    else:
        assert "Failed verification output" not in output["prompt"]
    assert json.loads(output["prompt"].split("Task snapshot:\n", 1)[1]) == payload["snapshot"]
    for flag in [
        "--print",
        "--no-session",
        "--no-approve",
        "--no-mcp",
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
        "--no-themes",
        "--offline",
    ]:
        assert flag in output["args"]
    assert output["args"][-4:] == ["--model", "chosen", "--tools", "read,bash,edit,write"]
