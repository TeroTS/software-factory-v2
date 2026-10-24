import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from software_factory.sandbox import PI_FLAGS

NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node is needed to exercise the sandbox Pi wrapper")
@pytest.mark.parametrize(
    "outcome", ["success", "repair", "missing-model", "catalog-failure", "execution-failure", "terminated"]
)
def test_agent_wrapper_uses_ephemeral_credentials_and_exact_model(tmp_path: Path, outcome: str) -> None:
    wrapper = Path(__file__).resolve().parents[1] / "src/software_factory/sandbox_agent.mjs"
    pi = tmp_path / "pi"
    pi.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, signal, sys\n"
        "home = pathlib.Path(os.environ['PI_CODING_AGENT_DIR'])\n"
        "assert '--no-context-files' in sys.argv\n"
        "if '--list-models' in sys.argv:\n"
        f"    print('github-copilot {'other' if outcome == 'missing-model' else 'chosen'} 128k 4k')\n"
        f"    sys.exit({7 if outcome == 'catalog-failure' else 0})\n"
        "else:\n"
        "    print(json.dumps({'args': sys.argv[1:], 'auth': json.loads((home/'auth.json').read_text()), "
        "'models': json.loads((home/'models.json').read_text()), 'prompt': sys.stdin.read(), "
        "'home': str(home)}), flush=True)\n"
        f"    if {outcome == 'execution-failure'}: sys.exit(8)\n"
        f"    if {outcome == 'terminated'}: os.kill(os.getpid(), signal.SIGTERM)\n"
    )
    pi.chmod(0o755)
    payload = {
        "snapshot": {"number": 7, "title": "task", "body": None},
        "bearer": "private-bearer",
        "endpoint": "https://api.business.githubcopilot.com",
        "model": "chosen",
        "flags": PI_FLAGS + ["--no-context-files"],
    }
    if outcome == "repair":
        payload["verification_output"] = "assert actual == expected\nverification stderr"
    result = subprocess.run(
        [NODE, str(wrapper)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
    )
    if outcome in {"missing-model", "catalog-failure"}:
        assert result.returncode != 0
        assert "configured Copilot model is unavailable" in result.stderr
        assert "private-bearer" not in result.stderr
        return
    expected = {"success": 0, "repair": 0, "execution-failure": 8, "terminated": 1}
    assert result.returncode == expected[outcome], result.stderr
    output = json.loads(result.stdout)
    assert not Path(output["home"]).exists()
    assert output["auth"] == {"github-copilot": {"type": "api_key", "key": "private-bearer"}}
    assert output["models"]["providers"]["github-copilot"]["baseUrl"] == payload["endpoint"]
    assert "private-bearer" not in output["prompt"]
    assert "COMPOSE_PROJECT_NAME" in output["prompt"]
    assert "software-factory.run-id=$FACTORY_RUN_ID" in output["prompt"]
    assert "linux/arm64" in output["prompt"]
    assert "current host-matched user" in output["prompt"]
    assert "explicit sudo -n only for system installs" in output["prompt"]
    assert "never retry permission errors automatically as root" in output["prompt"]
    assert "Cleanup will not repair workspace ownership or permissions" in output["prompt"]
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
        "--no-context-files",
    ]:
        assert flag in output["args"]
    assert output["args"][-4:] == ["--model", "chosen", "--tools", "read,bash,edit,write"]
