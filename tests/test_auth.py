import base64
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import pytest

from software_factory.process import Commands, FactoryError


@pytest.fixture
def host_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    directory = tmp_path / ".config/software-factory"
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
    return directory


class Exchange(Commands):
    def __init__(self, directory: Path) -> None:
        super().__init__(deadline=time.monotonic() + 30, log=directory / "run.log")
        self.exchanges = []
        self.response = None

    def run(self, args, phase, **kwargs):
        if phase == "GitHub App token exchange":
            self.exchanges.append((args, kwargs))
            if isinstance(self.response, Exception):
                raise self.response
            return self.response or json.dumps(
                {
                    "token": f"private-installation-token-{len(self.exchanges)}",
                    "expires_at": datetime.fromtimestamp(time.time() + 3600, UTC).isoformat(),
                    "permissions": {
                        "contents": "write",
                        "issues": "write",
                        "pull_requests": "write",
                        "metadata": "read",
                    },
                }
            )
        return super().run(args, phase, **kwargs)


def test_app_signs_real_jwt_and_scopes_private_exchange(host_credentials, monkeypatch) -> None:
    from software_factory.auth import GitHubApp

    monkeypatch.setenv("GH_TOKEN", "unrelated-personal-token")
    monkeypatch.setenv("GITHUB_TOKEN", "other-personal-token")
    monkeypatch.setenv("GH_DEBUG", "api")
    app = GitHubApp.load("owner/repo")
    commands = Exchange(host_credentials)
    env = app.environment(commands)
    args, kwargs = commands.exchanges[0]
    assert args[:2] == ["curl", "--disable"]
    settings = {
        key: json.loads(value) for key, value in (line.split(" = ", 1) for line in kwargs["input"].splitlines())
    }
    assert settings["url"] == "https://api.github.com/app/installations/456/access_tokens"
    assert kwargs["private"] is True
    assert json.loads(settings["data"]) == {
        "repositories": ["repo"],
        "permissions": {"contents": "write", "issues": "write", "pull_requests": "write"},
    }
    assert settings["header"].startswith("Authorization: Bearer ")
    jwt = settings["header"].removeprefix("Authorization: Bearer ")
    assert "GH_TOKEN" not in kwargs["env"]
    header, claims, signature = jwt.split(".")

    def decode(value):
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

    assert json.loads(decode(header)) == {"alg": "RS256", "typ": "JWT"}
    data = json.loads(decode(claims))
    assert data["iss"] == "123"
    assert data["iat"] <= time.time() < data["exp"] <= time.time() + 600
    public = host_credentials / "public.pem"
    subprocess.run(
        ["openssl", "pkey", "-in", str(host_credentials / "github-app.pem"), "-pubout", "-out", str(public)],
        capture_output=True,
        check=True,
    )
    sig = host_credentials / "signature"
    sig.write_bytes(decode(signature))
    result = subprocess.run(
        ["openssl", "dgst", "-sha256", "-verify", str(public), "-signature", str(sig)],
        input=f"{header}.{claims}".encode(),
        capture_output=True,
    )
    assert result.returncode == 0
    assert env["GH_TOKEN"] == "private-installation-token-1"
    assert env["GH_HOST"] == "github.com"
    assert "GITHUB_TOKEN" not in env and "GH_DEBUG" not in env
    assert jwt not in " ".join(args)
    assert env["GH_TOKEN"] in commands.secrets
    assert not commands.log.exists(), "signing and token exchange must not produce retained output"


@pytest.mark.parametrize("status", [201, 401, 403])
def test_real_http_exchange_uses_bearer_header_without_arguments_or_retries(host_credentials, status) -> None:
    from software_factory.auth import GitHubApp

    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append((self.path, self.headers["Authorization"], payload))
            self.send_response(status)
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "token": "wire-private-token",
                        "expires_at": datetime.fromtimestamp(time.time() + 3600, UTC).isoformat(),
                        "permissions": {"contents": "write", "issues": "write", "pull_requests": "write"},
                    }
                ).encode()
            )

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    class Wire(Commands):
        def run(self, args, phase, **kwargs):
            if phase == "GitHub App token exchange":
                assert args[0] == "curl", "gh's automatic token scheme does not authenticate App JWTs"
                assert kwargs["private"] is True
                assert not any("Bearer" in arg for arg in args)
                kwargs["input"] = kwargs["input"].replace(
                    "https://api.github.com", f"http://127.0.0.1:{server.server_port}"
                )
            return super().run(args, phase, **kwargs)

    commands = Wire(log=host_credentials / "wire.log")
    try:
        app = GitHubApp.load("owner/repo")
        if status == 201:
            assert app.environment(commands)["GH_TOKEN"] == "wire-private-token"
        else:
            with pytest.raises(FactoryError, match="exchange"):
                app.environment(commands)
        assert len(received) == 1
        path, authorization, payload = received[0]
        assert path == "/app/installations/456/access_tokens"
        assert authorization.startswith("Bearer ")
        assert len(authorization.removeprefix("Bearer ").split(".")) == 3
        assert payload["repositories"] == ["repo"]
        assert not commands.log.exists()
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_cached_tokens_renew_before_operation_and_register_with_each_budget(host_credentials, monkeypatch) -> None:
    from software_factory.auth import GitHubApp

    now = time.time()
    monkeypatch.setattr("software_factory.auth.time.time", lambda: now)
    app = GitHubApp.load("owner/repo")
    first = Exchange(host_credentials)
    original = app.environment(first)["GH_TOKEN"]
    assert app.environment(first)["GH_TOKEN"] == original
    assert len(first.exchanges) == 1
    second = Exchange(host_credentials)
    assert app.environment(second)["GH_TOKEN"] == original
    assert second.exchanges == []
    assert original in second.secrets
    now += 2401
    assert app.environment(first)["GH_TOKEN"] != original
    assert len(first.exchanges) == 2
    assert original in first.secrets
    assert "private-installation-token-2" in first.secrets


@pytest.mark.parametrize(
    "defect",
    ["missing-config", "missing-key", "config-mode", "key-mode", "directory-mode", "symlink", "not-file", "owner"],
)
def test_unsafe_or_missing_credentials_fail_without_exposing_contents(host_credentials, monkeypatch, defect) -> None:
    from software_factory.auth import GitHubApp

    config = host_credentials / "github-app.json"
    key = host_credentials / "github-app.pem"
    if defect == "missing-config":
        config.unlink()
    elif defect == "missing-key":
        key.unlink()
    elif defect == "config-mode":
        config.chmod(0o644)
    elif defect == "key-mode":
        key.chmod(0o644)
    elif defect == "directory-mode":
        host_credentials.chmod(0o755)
    elif defect == "symlink":
        key.rename(host_credentials / "actual.pem")
        key.symlink_to(host_credentials / "actual.pem")
    elif defect == "not-file":
        key.unlink()
        key.mkdir()
    else:
        monkeypatch.setattr("software_factory.auth.os.geteuid", lambda: os.getuid() + 1)
    with pytest.raises(FactoryError, match="GitHub App") as error:
        GitHubApp.load("owner/repo")
    assert "PRIVATE KEY" not in str(error.value)


@pytest.mark.parametrize(
    "data",
    [
        "bad-json",
        [],
        {"app_id": True, "installation_id": 1},
        {"app_id": 1},
        {"app_id": 0, "installation_id": 2},
        {"app_id": 1, "installation_id": -2},
        {"app_id": "123", "installation_id": 2},
        {"app_id": 1, "installation_id": 2, "extra": 3},
    ],
)
def test_invalid_app_configuration_is_actionable(host_credentials, data) -> None:
    from software_factory.auth import GitHubApp

    (host_credentials / "github-app.json").write_text(data if isinstance(data, str) else json.dumps(data))
    with pytest.raises(FactoryError, match="GitHub App"):
        GitHubApp.load("owner/repo")


@pytest.mark.parametrize(
    "response",
    [
        "not-json",
        "null",
        "{}",
        '{"token":"private-token","expires_at":"bad"}',
        '{"token":"private-token","expires_at":"2000-01-01T00:00:00Z"}',
        '{"token":"private-token","expires_at":"2099-01-01T00:00:00"}',
        '{"token":"private-token\\n","expires_at":"2099-01-01T00:00:00Z"}',
        FactoryError("GitHub token exchange failed"),
    ],
)
def test_invalid_or_failed_exchange_never_falls_back_or_retries(host_credentials, response) -> None:
    from software_factory.auth import GitHubApp

    app = GitHubApp.load("owner/repo")
    commands = Exchange(host_credentials)
    commands.response = response
    with pytest.raises(FactoryError) as error:
        app.environment(commands)
    assert "private-token" not in str(error.value)
    assert len(commands.exchanges) == 1


@pytest.mark.parametrize("permission", ["workflows", "administration", "missing-issues"])
def test_exchange_rejects_broader_or_insufficient_permissions(host_credentials, permission) -> None:
    from software_factory.auth import GitHubApp

    commands = Exchange(host_credentials)
    data = {
        "token": "private-token",
        "expires_at": datetime.fromtimestamp(time.time() + 3600, UTC).isoformat(),
        "permissions": {"contents": "write", "issues": "write", "pull_requests": "write"},
    }
    if permission == "missing-issues":
        del data["permissions"]["issues"]
    else:
        data["permissions"][permission] = "write"
    commands.response = json.dumps(data)
    with pytest.raises(FactoryError, match="permissions"):
        GitHubApp.load("owner/repo").environment(commands)


def test_restart_reissues_from_host_files_and_redacts_every_live_token(host_credentials) -> None:
    from software_factory.auth import GitHubApp

    commands = Exchange(host_credentials)
    GitHubApp.load("owner/repo").environment(commands)
    GitHubApp.load("owner/repo").environment(commands)
    assert len(commands.exchanges) == 2
    secrets = list(commands.secrets)
    commands.run(["python3", "-c", "import sys; print(sys.stdin.read())"], "output", input="\n".join(secrets))
    output = commands.log.read_text()
    assert all(secret not in output for secret in secrets)
    assert "[REDACTED]" in output


def test_failed_renewal_does_not_reuse_old_token(host_credentials, monkeypatch) -> None:
    from software_factory.auth import GitHubApp

    now = time.time()
    monkeypatch.setattr("software_factory.auth.time.time", lambda: now)
    commands = Exchange(host_credentials)
    app = GitHubApp.load("owner/repo")
    app.environment(commands)
    now += 2401
    commands.response = FactoryError("GitHub App token exchange unavailable")
    with pytest.raises(FactoryError, match="exchange"):
        app.environment(commands)
    assert len(commands.exchanges) == 2


def test_invalid_signing_key_does_not_exchange_or_log(host_credentials) -> None:
    from software_factory.auth import GitHubApp

    (host_credentials / "github-app.pem").write_text("private-invalid-key")
    commands = Exchange(host_credentials)
    with pytest.raises(FactoryError, match="GitHub App") as error:
        GitHubApp.load("owner/repo").environment(commands)
    assert "private-invalid-key" not in str(error.value)
    assert commands.exchanges == []
    assert not commands.log.exists()
