# Explicitly provision/check an Ubuntu ARM64 factory host; never authenticate or start the runner.
import argparse
import grp
import hashlib
import json
import logging
import os
import platform
import pwd
import shutil
import stat
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path, PurePosixPath

from software_factory.process import Commands, FactoryError

PREFIX = Path("/opt/software-factory")
UBUNTU_PACKAGES = {
    "git": "1:2.43.0-1ubuntu7.4",
    "make": "4.3-4.1build2",
    "sudo": "1.9.15p5-3ubuntu5.24.04.4",
    "curl": "8.5.0-2ubuntu10.16",
    "ca-certificates": "20260816ubuntu0.24.04.1",
    "build-essential": "12.10ubuntu1",
    "pkg-config": "1.8.1-2build1",
    "libssl-dev": "3.0.13-0ubuntu3.16",
    "zlib1g-dev": "1:1.3.dfsg-3.1ubuntu2.3",
    "libbz2-dev": "1.0.8-5.1ubuntu0.1",
    "libreadline-dev": "8.2-4build1",
    "libsqlite3-dev": "3.45.1-1ubuntu2.8",
    "libffi-dev": "3.4.6-1build1",
    "liblzma-dev": "5.6.1+really5.4.5-1ubuntu0.4",
    "libncurses-dev": "6.4+20240113-1ubuntu2.2",
    "xz-utils": "5.6.1+really5.4.5-1ubuntu0.4",
    "gnupg": "2.4.4-2ubuntu17.6",
}
EXTERNAL_PACKAGES = {
    "docker-ce": "5:29.9.2-1~ubuntu.24.04~noble",
    "docker-ce-cli": "5:29.9.2-1~ubuntu.24.04~noble",
    "containerd.io": "2.4.2-3~ubuntu.24.04~noble",
    "docker-buildx-plugin": "0.38.1-1~ubuntu.24.04~noble",
    "docker-compose-plugin": "5.6.1-1~ubuntu.24.04~noble",
    "gh": "2.103.2",
}
PYTHON_SHA = "a97d5549e9ad81fe17159ed02c68774ad5d266c72f8d9a0b5a9c371fe85d902b"
NODE_SHA = "0b2d9f564b6594222a62c82e1df2efe119dd4a4aff29644f4dd325bf360b6bcc"
UV_SHA = "d0054db9ba0ec472ee6d28fa3eda94fb021b5e77c962f3bb1ff4b4fa7934e66d"
PI_SHA = "ae2785e870b81a8c8e1d44510a57b5ee0bfc9e974679ac2faaada4aabee3d3c0"
NODE_KEY_URL = "https://keys.openpgp.org/vks/v1/by-fingerprint/5BE8A3F6C8A5C01D106C0AD820B1A390B168D356"
NODE_KEY_SHA = "3adca70e0239a43803df385987be8303ed9abb3c2fb203feeda31dc6a5256731"
UBUNTU_SOURCES = "".join(
    f"deb [arch=arm64 signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] "
    f"http://ports.ubuntu.com/ubuntu-ports {suite} main\n"
    for suite in ("noble", "noble-updates", "noble-security")
)


# Reject unsupported hosts or non-administrative invocation before any preparation.
def validate_host() -> None:
    if platform.system() != "Linux" or platform.machine() != "aarch64":
        raise FactoryError("provisioning requires native Ubuntu 24.04 ARM64 Linux")
    release = platform.freedesktop_os_release()
    if release.get("ID") != "ubuntu" or release.get("VERSION_ID") != "24.04":
        raise FactoryError("provisioning requires Ubuntu 24.04 LTS")
    if os.geteuid() != 0:
        raise FactoryError("invoke provisioning explicitly as an administrator using sudo")


# Detect factory name/numeric-ID conflicts without modifying or renumbering accounts.
def validate_identity() -> None:
    for lookup, key in ((pwd.getpwnam, "factory"), (pwd.getpwuid, 2000)):
        try:
            user = lookup(key)
        except KeyError:
            continue
        if (user.pw_name, user.pw_uid, user.pw_gid) != ("factory", 2000, 2000):
            raise FactoryError("factory account/UID conflict; inspect existing accounts, do not renumber them")
    for lookup, key in ((grp.getgrnam, "factory"), (grp.getgrgid, 2000)):
        try:
            group = lookup(key)
        except KeyError:
            continue
        if (group.gr_name, group.gr_gid) != ("factory", 2000):
            raise FactoryError("factory group/GID conflict; inspect existing groups, do not renumber them")


# Create a managed file once; refuse symlinks or different existing content instead of overwriting it.
def write_once(path: Path, data: bytes) -> None:
    if path.is_symlink():
        raise FactoryError(f"existing managed path is a symlink: {path}")
    if path.exists():
        if path.read_bytes() != data:
            raise FactoryError(f"existing managed file differs; inspect it before provisioning: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
    path.chmod(0o644)


# Fetch HTTPS release bytes and require the recorded SHA-256; never retry with another source/version.
def download(url: str, digest: str, destination: Path) -> None:
    try:
        with urllib.request.urlopen(url, timeout=90) as response:
            if not response.geturl().startswith("https://"):
                raise FactoryError("release download redirected away from HTTPS")
            with destination.open("xb") as output:
                shutil.copyfileobj(response, output)
    except OSError:
        raise FactoryError(
            "release download failed; check HTTPS trust/source availability, not verification bypasses"
        ) from None
    with destination.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != digest:
        raise FactoryError("release checksum mismatch; stop and verify the recorded source with the operator")
    destination.chmod(0o644)


# Extract only the expected verified release tree, with data filtering and no existing destination replacement.
def extract(archive: Path, directory: Path, top: str) -> None:
    if (directory / top).exists() or (directory / top).is_symlink():
        raise FactoryError(f"existing release directory needs inspection: {directory / top}")
    with tarfile.open(archive) as stream:
        members = stream.getmembers()
        if not members or any(
            not PurePosixPath(item.name).parts
            or PurePosixPath(item.name).is_absolute()
            or ".." in PurePosixPath(item.name).parts
            or PurePosixPath(item.name).parts[0] != top
            for item in members
        ):
            raise FactoryError("release archive has an unexpected path")
        stream.extractall(directory, members=members, filter="data")


# Run a command as factory with an explicit tool path and no inherited administrator credentials/environment.
def as_factory(commands: Commands, args: list[str], phase: str, *, private: bool = False) -> str:
    home = pwd.getpwnam("factory").pw_dir
    path = (
        f"{home}/.local/bin:{PREFIX}/python-3.14.3/bin:{PREFIX}/node-v22.19.0-linux-arm64/bin:"
        f"{PREFIX}/uv-0.5.13/bin:/usr/bin:/bin"
    )
    return commands.run(
        [
            "runuser",
            "-u",
            "factory",
            "--",
            "env",
            "-i",
            f"HOME={home}",
            "USER=factory",
            "LOGNAME=factory",
            "LANG=C.UTF-8",
            f"PATH={path}",
            f"NPM_CONFIG_PREFIX={home}/.local",
            "NPM_CONFIG_REGISTRY=https://registry.npmjs.org/",
            "NPM_CONFIG_STRICT_SSL=true",
            "NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt",
            "UV_NATIVE_TLS=true",
            *args,
        ],
        phase,
        cwd=Path(home),
        private=private,
    )


# Return whether a top-level APT package is installed at exactly its recorded version.
def package_matches(commands: Commands, name: str, version: str) -> bool:
    try:
        value = commands.run(["dpkg-query", "-W", "-f=${db:Status-Status}\t${Version}", name], "inspect package")
    except FactoryError:
        return False
    return value.strip() == f"installed\t{version}"


# Install exact missing/mismatched packages from isolated signed sources; correct repeated state needs no update.
def install_apt(commands: Commands, work: Path, packages: dict[str, str], sources: str) -> None:
    needed = [f"{name}={version}" for name, version in packages.items() if not package_matches(commands, name, version)]
    if not needed:
        return
    work.mkdir(parents=True, exist_ok=True)
    work.chmod(0o755)
    write_once(work / "sources.list", sources.encode())
    (work / "lists").mkdir(exist_ok=True)
    options = [
        "-o",
        f"Dir::Etc::sourcelist={work}/sources.list",
        "-o",
        "Dir::Etc::sourceparts=-",
        "-o",
        f"Dir::State::lists={work}/lists",
        "-o",
        "APT::Update::Error-Mode=any",
    ]
    commands.run(["apt-get", *options, "update"], "authenticate package metadata")
    commands.run(
        ["apt-get", *options, "install", "--yes", "--no-remove", "--no-install-recommends", *needed],
        "install pinned packages",
        env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
    )


# Install pinned Ubuntu packages first, then authenticate only the official Docker/GitHub repositories.
def install_packages(commands: Commands, work: Path) -> None:
    install_apt(commands, work / "ubuntu", UBUNTU_PACKAGES, UBUNTU_SOURCES)
    if all(package_matches(commands, name, version) for name, version in EXTERNAL_PACKAGES.items()):
        return
    sources = UBUNTU_SOURCES
    for name, url, digest, repository, suite in (
        (
            "docker",
            "https://download.docker.com/linux/ubuntu/gpg",
            "1500c1f56fa9e26b9b8f42452a553675796ade0807cdce11975eb98170b3a570",
            "https://download.docker.com/linux/ubuntu",
            "noble stable",
        ),
        (
            "gh",
            "https://cli.github.com/packages/githubcli-archive-keyring.gpg",
            "6084d5d7bd8e288441e0e94fc6275570895da18e6751f70f057485dc2d1a811b",
            "https://cli.github.com/packages",
            "stable main",
        ),
    ):
        key = work / f"{name}.key"
        download(url, digest, key)
        keyring = key
        if name == "docker":
            keyring = work / "docker.gpg"
            commands.run(["gpg", "--batch", "--dearmor", "--output", str(keyring), str(key)], "prepare Docker keyring")
            keyring.chmod(0o644)
        sources += f"deb [arch=arm64 signed-by={keyring}] {repository} {suite}\n"
    install_apt(commands, work / "external", EXTERNAL_PACKAGES, sources)


# Create only the missing fixed account/group, add Docker membership, and supply account-scoped login tool paths.
def ensure_account(commands: Commands) -> None:
    try:
        grp.getgrnam("factory")
    except KeyError:
        commands.run(["groupadd", "--gid", "2000", "factory"], "create factory group")
    try:
        pwd.getpwnam("factory")
    except KeyError:
        commands.run(
            ["useradd", "--uid", "2000", "--gid", "2000", "--create-home", "--shell", "/bin/bash", "factory"],
            "create factory account",
        )
    if grp.getgrnam("docker").gr_gid not in os.getgrouplist("factory", 2000):
        commands.run(["usermod", "--append", "--groups", "docker", "factory"], "grant factory Docker access")
    profile = (
        "# Factory host tools apply only to the fixed account; no credentials or sudo policy.\n"
        'if [ "$(id -u)" = 2000 ]; then\n'
        f'    export PATH="$HOME/.local/bin:{PREFIX}/python-3.14.3/bin:{PREFIX}/node-v22.19.0-linux-arm64/bin:'
        f'{PREFIX}/uv-0.5.13/bin:$PATH"\n'
        '    export NPM_CONFIG_PREFIX="$HOME/.local"\n'
        "    export NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt\n"
        "    export UV_NATIVE_TLS=true\n"
        "fi\n"
    )
    write_once(Path("/etc/profile.d/software-factory.sh"), profile.encode())
    commands.run(["systemctl", "enable", "--now", "docker"], "start local Docker engine")


# Require an exact version token, allowing only a separate trailing build description.
def check_version(commands: Commands, args: list[str], expected: str, *, factory: bool = False) -> None:
    output = as_factory(commands, args, "check tool version") if factory else commands.run(args, "check tool version")
    value = output.strip()
    if value != expected and not value.startswith(expected + " "):
        raise FactoryError(
            f"tool version mismatch; expected {expected}; inspect installed state without overwriting it"
        )


# Reuse an existing release only after execution/version validation; partial/symlinked installs fail visibly.
def reuse_release(commands: Commands, binary: Path, expected: str) -> bool:
    root = binary.parent.parent
    if root.is_symlink():
        raise FactoryError(f"existing release is a symlink; inspect it: {root}")
    if root.exists():
        check_version(commands, [str(binary), "--version"], expected)
        return True
    return False


# Build checksum-verified official Python separately from system Python; never replace /usr/bin executables.
def install_python(commands: Commands, work: Path) -> None:
    prefix = PREFIX / "python-3.14.3"
    if reuse_release(commands, prefix / "bin/python3", "Python 3.14.3"):
        return
    source = work / "Python-3.14.3.tar.xz"
    download("https://www.python.org/ftp/python/3.14.3/Python-3.14.3.tar.xz", PYTHON_SHA, source)
    extract(source, work, "Python-3.14.3")
    directory = work / "Python-3.14.3"
    commands.run(["./configure", f"--prefix={prefix}", "--with-ensurepip=install"], "configure Python", cwd=directory)
    commands.run(["make", "-j", str(min(os.cpu_count() or 1, 4))], "build Python", cwd=directory)
    commands.run(["make", "install"], "install separate Python", cwd=directory)


# Verify the Node release signature and checksum before extracting its official native binary distribution.
def install_node(commands: Commands, work: Path) -> None:
    top = "node-v22.19.0-linux-arm64"
    if reuse_release(commands, PREFIX / top / "bin/node", "v22.19.0"):
        return
    key = work / "node.asc"
    download(NODE_KEY_URL, NODE_KEY_SHA, key)
    commands.run(
        ["gpg", "--batch", "--dearmor", "--output", str(work / "node.gpg"), str(key)], "prepare Node signing key"
    )
    for name, digest in (
        ("SHASUMS256.txt", "de2602986573174f8815e5c66a157950132166113edddd9124c30784303ede31"),
        ("SHASUMS256.txt.sig", "a707e2c47cc87728a7664a1f215d806b14b29cd116fcb4e2f4662325a0ce3298"),
    ):
        download(f"https://nodejs.org/dist/v22.19.0/{name}", digest, work / name)
    commands.run(
        ["gpgv", "--keyring", str(work / "node.gpg"), str(work / "SHASUMS256.txt.sig"), str(work / "SHASUMS256.txt")],
        "verify Node release signature",
    )
    if f"{NODE_SHA}  {top}.tar.xz" not in (work / "SHASUMS256.txt").read_text().splitlines():
        raise FactoryError("signed Node manifest does not match the pinned ARM64 release")
    archive = work / f"{top}.tar.xz"
    download(f"https://nodejs.org/dist/v22.19.0/{top}.tar.xz", NODE_SHA, archive)
    PREFIX.mkdir(parents=True, exist_ok=True)
    extract(archive, PREFIX, top)


# Install the checksum-verified official uv binaries in a dedicated version directory, with no installer script.
def install_uv(commands: Commands, work: Path) -> None:
    prefix = PREFIX / "uv-0.5.13"
    if reuse_release(commands, prefix / "bin/uv", "uv 0.5.13"):
        return
    top = "uv-aarch64-unknown-linux-gnu"
    archive = work / f"{top}.tar.gz"
    download(f"https://github.com/astral-sh/uv/releases/download/0.5.13/{top}.tar.gz", UV_SHA, archive)
    extract(archive, work, top)
    (prefix / "bin").mkdir(parents=True)
    for name in ("uv", "uvx"):
        shutil.copyfile(work / top / name, prefix / "bin" / name)
        (prefix / "bin" / name).chmod(0o755)


# Install only the pinned npm Pi archive as factory; preserve its home/authentication on repeated invocation.
def install_pi(commands: Commands, work: Path) -> None:
    binary = Path(pwd.getpwnam("factory").pw_dir) / ".local/bin/pi"
    if binary.exists() or binary.is_symlink():
        check_version(commands, [str(binary), "--version"], "1.3.0", factory=True)
        return
    archive = work / "pi-coding-agent-1.3.0.tgz"
    download("https://registry.npmjs.org/@earendil-works/pi-coding-agent/-/pi-coding-agent-1.3.0.tgz", PI_SHA, archive)
    as_factory(
        commands,
        ["npm", "install", "--global", "--no-audit", "--no-fund", str(archive)],
        "install Pi as factory",
        private=True,
    )


# Validate tools, identity, writable home, denied general host sudo, and actual native Docker access.
def check_readiness(commands: Commands) -> None:
    for name, version in (UBUNTU_PACKAGES | EXTERNAL_PACKAGES).items():
        if not package_matches(commands, name, version):
            raise FactoryError(f"required APT package version is not installed: {name}={version}")
    if (
        as_factory(commands, ["id", "-u"], "check factory UID").strip() != "2000"
        or as_factory(commands, ["id", "-g"], "check factory GID").strip() != "2000"
    ):
        raise FactoryError("factory execution identity is not 2000:2000")
    for args, version in (
        (["python3", "--version"], "Python 3.14.3"),
        (["node", "--version"], "v22.19.0"),
        (["uv", "--version"], "uv 0.5.13"),
        (["pi", "--version"], "1.3.0"),
    ):
        check_version(commands, args, version, factory=True)
    as_factory(
        commands,
        [
            "python3",
            "-I",
            "-c",
            "import bz2,ctypes,ensurepip,lzma,os,pathlib,readline,sqlite3,ssl,zlib; "
            "p=pathlib.Path.home(); assert os.access(p,os.R_OK|os.W_OK|os.X_OK); "
            "assert p.stat().st_uid==2000",
        ],
        "check Python modules and factory home",
    )
    for args in (
        ["git", "--version"],
        ["make", "--version"],
        ["curl", "--version"],
        ["gh", "--version"],
        ["npm", "--version"],
        ["docker", "compose", "version"],
        ["docker", "buildx", "version"],
    ):
        as_factory(commands, args, "check factory tools")
    try:
        as_factory(commands, ["sudo", "-n", "/bin/sh", "-c", "exit 0"], "check host sudo is denied", private=True)
    except FactoryError:
        pass
    else:
        raise FactoryError("factory has general passwordless host sudo; remove that grant explicitly before readiness")
    check_socket()
    check_engine(commands)


# Run explicit install/check phases with private command diagnostics; partial failure never reports readiness.
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicit Ubuntu 24.04 ARM64 factory host provisioning")
    parser.add_argument(
        "--check", action="store_true", help="check readiness only, without installations or account changes"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    log = None
    try:
        validate_host()
        validate_identity()
        fd, filename = tempfile.mkstemp(prefix="factory-provision-", suffix=".log", dir="/var/tmp")
        os.close(fd)
        log = Path(filename)
        commands = Commands(deadline=time.monotonic() + 3600, log=log)
        if not args.check:
            with tempfile.TemporaryDirectory(prefix="factory-provision-", dir="/var/tmp") as directory:
                work = Path(directory)
                work.chmod(0o755)
                install_packages(commands, work)
                ensure_account(commands)
                install_python(commands, work)
                install_node(commands, work)
                install_uv(commands, work)
                install_pi(commands, work)
        check_readiness(commands)
    except (FactoryError, OSError, ValueError, KeyError, tarfile.TarError) as error:
        reason = str(error) if isinstance(error, FactoryError) else "host state or installation operation failed"
        if reason == "issue-run deadline expired":
            reason = "host provisioning exceeded its one-hour command budget"
        logging.getLogger("software_factory").error(
            "Provisioning failed; host may be partially prepared: %s. Private command log: %s",
            reason,
            log or "not created",
        )
        return 1
    print(
        "Factory host ready (2000:2000, native local Docker). Authenticate gh/Pi manually next. "
        f"Private command log: {log}"
    )
    return 0


# Require the actual local Docker socket and reject world-writable access without changing its permissions.
def check_socket() -> None:
    try:
        mode = os.stat("/var/run/docker.sock").st_mode
    except OSError:
        raise FactoryError("Docker socket is unavailable; inspect the local engine service") from None
    if not stat.S_ISSOCK(mode) or mode & stat.S_IWOTH:
        raise FactoryError("Docker socket is missing/incompatible or world-writable; inspect host configuration")


# Prove factory-account access to the local native engine, not merely administrator access or CLI availability.
def check_engine(commands: Commands) -> None:
    output = as_factory(
        commands,
        ["docker", "--host", "unix:///var/run/docker.sock", "info", "--format", "{{json .}}"],
        "factory Docker access",
    )
    try:
        result = json.loads(output)
    except json.JSONDecodeError:
        raise FactoryError("local Docker engine returned an invalid readiness result") from None
    if (
        not isinstance(result, dict)
        or result.get("OSType") != "linux"
        or result.get("Architecture") not in ("aarch64", "arm64")
    ):
        raise FactoryError("factory Docker access requires a native Linux ARM64 engine")
