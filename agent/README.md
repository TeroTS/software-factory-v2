# Shared agent image

Build from a factory-owned checkout on the provisioned Ubuntu 24.04 ARM64 Lima
guest's Linux disk, logged in as `factory` (UID/GID 2000:2000):

```sh
docker build --platform linux/arm64 -t software-factory-agent:1.0.0 agent
FACTORY_AGENT_IMAGE_TESTS=1 uv run --frozen pytest tests/test_startup_docker.py -q
```

The operator builds before startup. The runner only inspects a local image and
executes a short native tool check with `--pull=never`; it never builds/pulls or
uses emulation. Startup pins the selected tag to its immutable image ID for the
session. Restart after rebuilding/retagging to adopt changes. The tests require
an already-built image (`FACTORY_AGENT_IMAGE` can override the reference).

## Pinned baseline

[Dockerfile](Dockerfile) pins upstream image manifests by digest. Debian tool and
transitive package versions resolve from the fixed signed **2026-03-01 UTC**
Bookworm/Bookworm-security snapshot, with expiry checks disabled only for that
historical snapshot, not signature verification. Python and Node come from their
pinned official images; Docker CLI/plugins come from the pinned official Docker
CLI image. Pi and uv use exact package versions. No target files or host
configuration are copied into the image.

| Tool | Baseline |
| --- | --- |
| Base | Python 3.14.3 slim Bookworm, digest in Dockerfile |
| Node.js / npm | 22.19.0 / 10.9.3 |
| Pi | `@earendil-works/pi-coding-agent@1.3.0` |
| Python / uv | 3.14.3 / 0.5.13 |
| Docker CLI | 28.4.0 |
| Docker Compose | 2.39.4 |
| Docker buildx | Included by the pinned Docker CLI image |
| Bash | 5.2.15 |
| Git | 2.39.5 |
| Make | 4.3 |
| sudo | 1.9.13p3 (Debian revision from the fixed snapshot) |
| C/C++ compiler | GCC/G++ 12.2.0 |
| curl | 7.88.1 |
| tar / unzip | 1.34 / 6.00 |
| CA certificates / Linux utilities | Fixed Debian snapshot and base manifest |

The build includes `build-essential`, standard utilities, curl, certificates,
tar, unzip, and sudo. The image selects account/group `factory`, UID/GID
2000:2000; setup, Pi, and verification run as that fixed non-root identity.
Explicit `sudo -n` commands install
nonbaseline system tools without prompting. Elevation is not technically restricted
to installs, and is not a security boundary. Do not run whole setup scripts or
workspace builds as root or retry permission errors automatically with sudo.
Node/npm/npx, Python/uv, and Docker/Compose/buildx are on their standard paths. `UV_LINK_MODE=copy` avoids cross-filesystem link assumptions. The image
leaves uv's Python download policy at its default, so target setup can obtain
another Python version when required.

Pins provide a repeatable baseline, not a security-update promise or a complete
transitive npm lockfile. Review/rebuild with updated pins and rerun native checks
when changing the baseline. There are no credentials, host authentication mounts,
Docker daemon, or target-specific dependencies in the image. Runtime engine access
grants effective engine/host control during issue execution; this image is not an isolation
boundary.

## Fixed-identity startup and migration

Rebuild the image explicitly and restart the runner after upgrading. Startup
requires the provisioned Ubuntu 24.04 ARM64 host and effective UID/GID 2000:2000;
it rejects root and other identities rather than switching accounts. Old images
from the arbitrary-host-user model are incompatible. No new image tag policy or
automatic account/configuration/artifact migration is introduced.

The factory account/group, private `/tmp/factory-home`, writable XDG cache and npm
user-local prefix are created at build time. The prefix's `bin` directory leads
PATH. Startup validates the image's actual default execution identity, account,
writable directories, tools, and noninteractive sudo without a root account-setup
exec or account/shadow/group mutation. The socket-free startup probe does not
prove issue-run Docker access. Each issue-run agent receives the selected local
socket's actual numeric GID through `--group-add`. Before setup, the runner uses
`docker exec -i` without a user override to validate UID/GID 2000:2000,
supplementary socket membership, and engine access. Neither agent creation nor
exec initializes accounts or edits account/shadow/group files; access failure
ends the run without socket permission changes or root fallback.

Only factory has passwordless sudo configured by the image, with root HOME
selection. Setup scripts that assumed root need adaptation: use explicit
`sudo -n apt-get ...` for OS packages and ordinary user commands for project
installs/builds.
The image installs sudo from the same signed Debian snapshot.

No host home/settings are mounted. Deliberately root-owned or mode-restricted
workspace output is not repaired: inaccessible required publication files block
publication. Service-private data should use disposable owned volumes, not
workspace binds. Fixed identity and account-scoped sudo are not security isolation
against an agent with Docker engine access.

## Verification boundary

`tests/test_startup_docker.py` executes these native tool checks and the real
CLI startup-to-polling path against local Docker. Authentication/GitHub are
scripted, and no issue is claimed. The probe runs without network access, mounts,
or credentials and is removed before polling. This is not acceptance of
Docker-enabled issue execution by itself. The [Docker suite](../tests/test_docker_integration.py)
and [CLI issue E2E](../tests/test_issue_docker.py) additionally use this image for
real application builds, ordinary Compose services, same-path sibling mounts,
socket access, a target-installed tool, host-usable ordinary files without repair,
and scoped cleanup.
Pi/authentication/GitHub boundaries are scripted; no live provider request or
GitHub write is made. macOS browser access to guest services requires a separate
check; it cannot be inferred from Linux CI.

New agents use the image's unmodified Docker executable directly; no runtime
Docker-executable installation or relocation is needed. The fixed-identity
migration above does require an image rebuild. Startup validates
the native engine/shared image. Factory-owned containers explicitly request
`--platform linux/arm64` and `--pull=never`; target commands inherit
`DOCKER_DEFAULT_PLATFORM=linux/arm64`. Target scripts must use native-compatible
images/tools. The factory does not intercept Docker commands or guarantee rejection
of explicit platform overrides, which may invoke engine-supported emulation.
Actual Docker/setup/verification failures remain visible without factory-selected
emulation or replacement dependencies. Existing containers retain their current
filesystem until removed; this change applies to newly created agents.

See [operator setup](../README.md#operator-setup) for TOML, target preparation,
resource ownership conventions, and first-pass execution behavior.
