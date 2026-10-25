# Current Slice

Status: done

## Slice Goal
- Let the operator explicitly provision a Linux factory host ready for manual authentication and later runner startup.

## Slice Boundary
- Actor: Operator.
- Trigger: An explicitly authorized Ubuntu Server 24.04 LTS ARM64 host is available for factory setup.
- Action: Prepare the local Lima host using the repository-maintained provisioning entrypoint/runbook.
- Visible outcome: The fixed factory account and validated prerequisites are ready for manual authentication and runner startup.
- Authoritative state transition: Unprepared Linux host → provisioned factory host with verified identity/tool access.
- Include readiness validation and failure reporting, without issue processing or automatic authentication.

## Stories In Scope
- `US-08 Provision a Linux factory host`

## Stories Completed In This Slice
- `US-08 Provision a Linux factory host`

## Stories Remaining In This Slice
- None.

## Contract Inputs
- `docs/contracts.md`, Contract 9: explicit provisioning, fixed account, sources/verification, Lima/native storage, repeatability, readiness, failure handling, and local-VM-only acceptance.
- `docs/contracts.md`, Contract 1: authentication, image build, and runner startup remain subsequent operator actions; preserve CLI/TOML.
- No factory-owned HTTP API or `openapi.yaml` applies.

## Decision Inputs
- `DECISIONS.md`, Operations / Deployment and Open Questions: operator-approved local-VM-only acceptance supersedes separate production-like host repetition; explicit agreement before installation/allocation, verified release/package inputs before installation commands, and no automatic trust/source/version fallback remain required.

## Shared State Required Now
- Host account/group `factory`, UID/GID `2000:2000`, Docker membership, no general host passwordless sudo.
- Operator-approved persistent Lima 2.2.1 VM: 4 CPUs, 8 GiB RAM, 40 GiB disk, native Linux execution data, no macOS directory sharing, and Rancher stopped while Lima is in use.
- SSH plus one explicit guest TCP 8080 → macOS 127.0.0.1:8080 forward; other automatic service forwards suppressed. Rosetta/containerd disabled.
- Recorded source/package/release pins and verification evidence; existing correct account/tool installations and previous credentials/repositories/diagnostics preserved on repeated provisioning.
- Operator-approved local public Zscaler CA, fingerprint `04F61F1D13AAE1D16573DC2C37F796FDF4AC97713A6959EBB11D2473958B1A53`. It was installed only in the authorized guest; generic provisioning does not copy/add trust roots.
- No issue-run state, new TOML fields, credentials, or recovery state.

## Operations / Endpoints / Surfaces In This Slice
- `scripts/provision-host`: explicit Ubuntu system-Python bootstrap, separate from `scripts/setup`.
- `src/software_factory/provision.py`: host/identity checks, authenticated pinned APT installation, verified official Python/Node/uv releases, user-scoped pinned Pi installation, factory login paths, native Docker readiness, and `--check` without installation/account changes.
- Installation uses `/opt/software-factory` version directories, factory-local npm/Pi, and a factory-only `/etc/profile.d/software-factory.sh`; system Python is unchanged. Commands share a one-hour budget and private 0600 logs, with safe partial-failure diagnostics.
- `infra/lima/factory.yaml` and README operator commands describe VM setup/provisioning. Exact resolved source versions, verification provenance, implementation notes, and delivery evidence are recorded only in this slice note.
- Durable docs contain operator guidance, standing rules, and architecture boundaries—not story status, implementation history, or test results. Existing runner/image behavior is unchanged.
- The operator explicitly removed deployment/testing outside this local VM from scope. No separate-host acceptance blocker remains, and US-09 has not been started.
- Consolidated delivery tracking and source-verification records into this note. Removed story/status/history from durable guidance; preserved concurrent removal of `docs/workflows/` and `docs/plans/` and relocation of the user-owned simplified workflow without recreating or editing those files.

## Tests Required
- Real Lima readiness E2E: `FACTORY_PROVISION_TESTS=1 uv run --frozen pytest tests/test_provision_lima.py -q` passed from the initial unprovisioned guest, then on repeated checks. It stages only trusted bootstrap code, installs/checks tools and actual factory Docker access, seeds private source/diagnostic sentinels, repeats provisioning, and confirms their content/ownership/mode survive. It removes only its own sentinels; bootstrap snapshots and private command logs remain.
- `tests/test_provision.py`: **56** unit/boundary cases cover unsupported/rootless invocation, name/ID conflicts, correct reuse, managed-file preservation/symlinks, unavailable downloads/HTTPS downgrade/checksum failure, Node signature/manifest failures, safe archives, exact signed APT arguments and installation failure, factory-only Pi/environment, version/home/UID/GID failures, forbidden general shell sudo, unusable socket/engine, malformed responses, phase ordering, and safe partial-failure/deadline diagnostics. External command/install failures are scripted, not destructive experiments on existing accounts.
- Test-first failures reproduced absent implementation, wrong wildcard forwarding defaults, missing uv system-CA selection, unsafe empty archive paths, missing socket/malformed engine diagnostics, and non-logging error reporting before the corresponding changes.
- Local `factory` VM creation and stop/start passed using the checksum-verified Ubuntu 20260926 ARM64 image. Guest checks confirmed Ubuntu 24.04/aarch64, four CPUs, ~7.7 GiB usable RAM, native root storage, and no virtiofs/9p/SSHFS mounts. Post-install root free space is ~35 GiB. Rancher is stopped. SSH access passed.
- Temporary HTTP fixtures proved macOS loopback 8080 reachability and non-forwarding of guest-reachable 18081; both were stopped. Initial host port 8081 unavailability was handled without changing an existing service. These are HTTP probes, not browser/Docker application-service evidence.
- Initial guest HTTPS failed on all required source hosts. After explicit CA approval/installation, verified HTTPS passed. Signed APT metadata, exact package versions, official archive checksums, Node's detached signature, and Pi registry integrity were checked/recorded before installation implementation.
- Factory login checks passed for 2000:2000, Python 3.14.3, Node 22.19.0, uv 0.5.13, Pi 1.3.0, and actual native local Docker. uv found the separate Python and resolved declared Ruff 0.17.2 over verified HTTPS with `--dry-run` (no installation). A probe initially retained the inaccessible administrator working directory; rerunning from factory HOME fixed the probe without permission changes. Provisioning commands already set the proper working directory.
- Final `FACTORY_PROVISION_TESTS=1 ./scripts/verify` passed format → lint → tests/coverage: **308 passed, 35 opt-in Docker/image checks skipped**, Python overall line/branch **99.34%**, provisioning module **100%**. An initial coverage decrease was investigated: root installation paths in the guest subprocess were not measured by host coverage; meaningful in-process external-boundary tests closed those gaps. Final coverage exceeds the prior **99.04%** baseline; the **80%** gate and exclusions are unchanged.
- `limactl validate infra/lima/factory.yaml`, shell syntax checking, CLI help without polling, and the prior documentation checks passed before consolidation. After this documentation-only cleanup, `git diff --check`, Markdown whitespace/fences, **52 local links/anchors**, canonical slice/source-evidence structure, and absence of story IDs in README/AGENTS/architecture passed. Behavior tests were not rerun because code was unchanged. No standalone type checker/Markdown linter is configured.
- No separate production-like host evidence is required under the revised operator-approved scope. Existing Docker/image issue-run suites were not enabled: Rancher is stopped and no shared agent image has been built in Lima. Their later command is `FACTORY_DOCKER_TESTS=1 FACTORY_AGENT_IMAGE_TESTS=1 ./scripts/verify` after explicit compatible image preparation; US-09/US-10 migration checks remain separate.

### Verified provisioning inputs

These inputs were resolved on the authorized Ubuntu 24.04 ARM64 guest on
2026-10-25 before installation commands were implemented. Verification records
are consolidated here rather than duplicated in operator or architecture docs.

The operator approved the public Zscaler root identified under Shared State.
Only that matching public certificate was installed at
`/usr/local/share/ca-certificates/factory-zscaler.crt`, followed by
`update-ca-certificates`. Verified HTTPS then passed for all required source hosts;
no private key was copied. This machine-specific trust step is not part of generic
provisioning.

APT authenticated Ubuntu metadata using the image's
`/usr/share/keyrings/ubuntu-archive-keyring.gpg`. Research-only isolated source/list
directories authenticated Docker and GitHub CLI InRelease/package indexes before
installation. No package installation or upgrade occurred during that research.

| Source | Suites/components | Signing identity |
| --- | --- | --- |
| `http://ports.ubuntu.com/ubuntu-ports` | noble, noble-updates, noble-security / main | Image-provided Ubuntu archive keyring. |
| `https://download.docker.com/linux/ubuntu` | noble / stable | [Official key](https://download.docker.com/linux/ubuntu/gpg), primary fingerprint `9DC858229FC7DD38854AE2D88D81803C0EBFCD88`. |
| `https://cli.github.com/packages` | stable / main | [Official keyring](https://cli.github.com/packages/githubcli-archive-keyring.gpg), current primary fingerprint `7F38BBB59D064DBCB3D84D725612B36462313325`; expired historical primary `2C6106201985B60E6C7AC87323F3D4EA75716059` was not the current signer. |

Exact top-level package versions resolved from authenticated indexes:

| Package | Version |
| --- | --- |
| git | `1:2.43.0-1ubuntu7.4` |
| make | `4.3-4.1build2` |
| sudo | `1.9.15p5-3ubuntu5.24.04.4` |
| curl | `8.5.0-2ubuntu10.16` |
| ca-certificates | `20260816ubuntu0.24.04.1` |
| build-essential | `12.10ubuntu1` |
| pkg-config | `1.8.1-2build1` |
| libssl-dev | `3.0.13-0ubuntu3.16` |
| zlib1g-dev | `1:1.3.dfsg-3.1ubuntu2.3` |
| libbz2-dev | `1.0.8-5.1ubuntu0.1` |
| libreadline-dev | `8.2-4build1` |
| libsqlite3-dev | `3.45.1-1ubuntu2.8` |
| libffi-dev | `3.4.6-1build1` |
| liblzma-dev | `5.6.1+really5.4.5-1ubuntu0.4` |
| libncurses-dev | `6.4+20240113-1ubuntu2.2` |
| xz-utils | `5.6.1+really5.4.5-1ubuntu0.4` |
| gnupg | `2.4.4-2ubuntu17.6` |
| docker-ce | `5:29.9.2-1~ubuntu.24.04~noble` |
| docker-ce-cli | `5:29.9.2-1~ubuntu.24.04~noble` |
| containerd.io | `2.4.2-3~ubuntu.24.04~noble` |
| docker-buildx-plugin | `0.38.1-1~ubuntu.24.04~noble` |
| docker-compose-plugin | `5.6.1-1~ubuntu.24.04~noble` |
| gh | `2.103.2` |

Transitive OS dependencies were authenticated by APT, not fully snapshotted.
Observed key-file SHA-256 values:

- Docker ASCII key: `1500c1f56fa9e26b9b8f42452a553675796ade0807cdce11975eb98170b3a570`.
- GitHub CLI binary keyring: `6084d5d7bd8e288441e0e94fc6275570895da18e6751f70f057485dc2d1a811b`.

The guest downloaded the following archives and matched their SHA-256 values
with HTTPS verification enabled:

| Release | Official archive | SHA-256 and verification basis |
| --- | --- | --- |
| Python 3.14.3 | [python.org source](https://www.python.org/ftp/python/3.14.3/Python-3.14.3.tar.xz) | `a97d5549e9ad81fe17159ed02c68774ad5d266c72f8d9a0b5a9c371fe85d902b`, matching the digest in official adjacent `.sigstore` metadata. Checksum/HTTPS verification, not a Sigstore signature claim. |
| Node.js 22.19.0 | [Official ARM64 archive](https://nodejs.org/dist/v22.19.0/node-v22.19.0-linux-arm64.tar.xz) | `0b2d9f564b6594222a62c82e1df2efe119dd4a4aff29644f4dd325bf360b6bcc`; `gpgv` verified detached `SHASUMS256.txt.sig` over `SHASUMS256.txt`, whose ARM64 entry matched. |
| uv 0.5.13 | [Official ARM64 GNU archive](https://github.com/astral-sh/uv/releases/download/0.5.13/uv-aarch64-unknown-linux-gnu.tar.gz) | `d0054db9ba0ec472ee6d28fa3eda94fb021b5e77c962f3bb1ff4b4fa7934e66d`, matching the official adjacent `.sha256` asset. |

Node signer Antoine du Hamel's fingerprint
`5BE8A3F6C8A5C01D106C0AD820B1A390B168D356` was listed in the
[versioned Node README](https://github.com/nodejs/node/blob/v22.19.0/README.md#release-keys).
The key was downloaded from
[keys.openpgp.org by full fingerprint](https://keys.openpgp.org/vks/v1/by-fingerprint/5BE8A3F6C8A5C01D106C0AD820B1A390B168D356),
with key-file SHA-256 `3adca70e0239a43803df385987be8303ed9abb3c2fb203feeda31dc6a5256731`.
The detached signature, not the earlier clear-signed-manifest experiment, was
used for installation verification.

The [npm registry release metadata](https://registry.npmjs.org/@earendil-works%2fpi-coding-agent/1.3.0)
confirmed `@earendil-works/pi-coding-agent@1.3.0` and Node `>=22.19.0`.
The downloaded tarball matched registry integrity
`sha512-V/WoCjA2hQSe3QLWIUB24cTRdtEdeLiIzkDqU5RMXV6VWuD+KGZnzVBMhglwdnQTySkehZsjt8a3g6Jd2g4nnw==`;
its SHA-256 was `ae2785e870b81a8c8e1d44510a57b5ee0bfc9e974679ac2faaada4aabee3d3c0`.
Pi was installed under factory with npm integrity/TLS checks retained, without
authentication.

## Not Now
- US-09 fixed host/image startup validation, baked image account/home/sudo, and fixed-identity ARM64 CI execution.
- US-10 actual agent exec supplementary socket membership, runtime account initialization removal, issue-to-PR regression, and full service/browser evidence.
- US-06 verification repairs and US-07 full manual-requeue acceptance are outside the migration backlog.
- Automatic authentication, live Copilot/GitHub checks, runner-managed provisioning, paid resources, general host passwordless sudo, account/artifact migration, permission repair, image build, or runner startup.
- Cloud access/allocation remains unauthorized. No live authentication, commit, or push was performed.

## Done When
- The authorized local Lima Ubuntu ARM64 host reaches independently checked readiness through the explicit provisioning entrypoint; no separate production-like deployment/testing is required.
- Repeated provisioning preserves correct state/credentials/repositories/diagnostics; conflicts, failed verification/installations, and unusable Docker access report failure rather than readiness.
- Tools use the accepted sources/pins and recorded verification evidence, without replacing system Python, silently substituting versions, or automatically upgrading.
- Manual authentication and later image build/startup remain separate; instructions accurately distinguish delivery from outstanding migration work.
- Required real readiness checks, failure regressions, formatting, lint, documentation checks, and the unchanged coverage gate pass.

## Completion Summary
- The operator can explicitly prepare/check the local Lima host with fixed identity `factory` 2000:2000, verified pinned tools, writable home, and actual native local Docker access, ready for manual authentication.
- Repeated provisioning preserves correct installations and retained source/diagnostic files; invalid inputs, unverifiable releases, installation failures, and unusable access fail visibly without account/permission repair or false readiness.
- Completed under the operator-approved local-VM-only scope. No cloud validation, authentication, image/startup/execution migration, commit, or push is claimed.

## Next Slice Recommendation
- `US-09 Start the runner with the fixed factory identity`: validate the provisioned host and baked image identity through startup-to-polling with scripted authentication/GitHub boundaries. Keep `US-10 Execute issue runs without runtime account initialization` in view for actual exec socket groups and obsolete initialization removal, without including that outcome in US-09. Both use local Lima acceptance; do not reintroduce separate production-like host testing.
