# Load private host GitHub App credentials and issue repository-scoped tokens without personal-login fallback.
import base64
import json
import os
import stat
import tempfile
import time
from datetime import datetime
from pathlib import Path

from software_factory.process import Commands, FactoryError

PERMISSIONS = {"contents": "write", "issues": "write", "pull_requests": "write"}


# Require exact private modes, regular files/directories, and current ownership without repairing operator files.
def private_path(path: Path, *, directory: bool = False) -> None:
    info = path.lstat()
    valid_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if not valid_type or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600):
        raise ValueError


# Encode JWT segments without padding; accept only factory-constructed JSON or signature bytes.
def encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


# Retain one installation identity and short-lived cached token shared by host API/Git operations.
class GitHubApp:
    # Bind validated IDs/key to the configured repository; no credentials are acquired until an operation needs them.
    def __init__(self, repository: str, app_id: int, installation_id: int, key: Path) -> None:
        self.repository = repository
        self.app_id = app_id
        self.installation_id = installation_id
        self.key = key
        self.token = ""
        self.expires = 0.0

    # Load the fixed host credential files; fail closed on missing, malformed, or insecure operator configuration.
    @classmethod
    def load(cls, repository: str) -> GitHubApp:
        directory = Path.home() / ".config/software-factory"
        config = directory / "github-app.json"
        key = directory / "github-app.pem"
        try:
            private_path(directory, directory=True)
            private_path(config)
            private_path(key)
            data = json.loads(config.read_text(encoding="utf-8"))
            if (
                not isinstance(data, dict)
                or set(data) != {"app_id", "installation_id"}
                or any(type(value) is not int or value <= 0 for value in data.values())
            ):
                raise ValueError
        except OSError, ValueError:
            raise FactoryError(
                "GitHub App credentials unavailable or invalid: require private factory-owned "
                "~/.config/software-factory (0700), github-app.json and github-app.pem (0600); "
                "JSON requires positive integer app_id and installation_id"
            ) from None
        return cls(repository, data["app_id"], data["installation_id"], key)

    # Sign a backdated App JWT using OpenSSL; retain its signature only in a private temporary directory.
    def bearer(self, commands: Commands) -> str:
        now = int(time.time())
        header = encode(b'{"alg":"RS256","typ":"JWT"}')
        claims = encode(json.dumps({"iat": now - 60, "exp": now + 540, "iss": str(self.app_id)}).encode())
        message = header + "." + claims
        try:
            private_path(self.key.parent, directory=True)
            private_path(self.key)
            with tempfile.TemporaryDirectory(prefix="factory-app-") as directory:
                signature = Path(directory) / "signature"
                commands.run(
                    ["openssl", "dgst", "-sha256", "-sign", str(self.key), "-out", str(signature)],
                    "GitHub App signing",
                    input=message,
                    private=True,
                )
                return message + "." + encode(signature.read_bytes())
        except OSError, ValueError, FactoryError:
            raise FactoryError(
                "GitHub App signing failed; inspect private key permissions, validity, and OpenSSL"
            ) from None

    # Supply an explicit GitHub.com token environment; renew before expiry without retrying any repository operation.
    def environment(self, commands: Commands, base: dict[str, str] | None = None) -> dict[str, str]:
        env = {
            key: value
            for key, value in (os.environ if base is None else base).items()
            if key not in {"GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN", "GH_DEBUG"}
        }
        env.update(GH_HOST="github.com", GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1")
        if self.expires - time.time() <= 1200:
            jwt = self.bearer(commands)
            commands.secrets.append(jwt)
            # GitHub requires Bearer for App JWTs; gh's automatic token scheme is unsuitable for this exchange.
            settings = {
                "url": f"https://api.github.com/app/installations/{self.installation_id}/access_tokens",
                "header": "Authorization: Bearer " + jwt,
                "data": json.dumps({"repositories": [self.repository.split("/")[1]], "permissions": PERMISSIONS}),
            }
            output = commands.run(
                [
                    "curl",
                    "--disable",
                    "--silent",
                    "--show-error",
                    "--fail",
                    "--request",
                    "POST",
                    "--header",
                    "Accept: application/vnd.github+json",
                    "--header",
                    "Content-Type: application/json",
                    "--config",
                    "-",
                ],
                "GitHub App token exchange",
                input="".join(f"{key} = {json.dumps(value)}\n" for key, value in settings.items()),
                env=env,
                private=True,
            )
            try:
                data = json.loads(output)
                token = data["token"]
                expires = datetime.fromisoformat(data["expires_at"])
                permissions = data["permissions"]
                if (
                    not isinstance(token, str)
                    or not token
                    or not token.isascii()
                    or not token.isprintable()
                    or any(char.isspace() for char in token)
                    or expires.tzinfo is None
                    or expires.timestamp() - time.time() < 1200
                    or not isinstance(permissions, dict)
                    or any(permissions.get(key) != value for key, value in PERMISSIONS.items())
                    or set(permissions) - {*PERMISSIONS, "metadata"}
                ):
                    raise ValueError
            except ValueError, TypeError, KeyError, OverflowError:
                raise FactoryError(
                    "GitHub App returned an invalid token, lifetime, or repository permissions"
                ) from None
            self.token, self.expires = token, expires.timestamp()
        if self.token not in commands.secrets:
            commands.secrets.append(self.token)
        return {**env, "GH_TOKEN": self.token}
