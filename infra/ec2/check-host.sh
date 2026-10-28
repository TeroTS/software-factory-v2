#!/bin/bash
# Inspect the synthesis-selected volume, retained mounts, factory identity/home,
# host sudo restrictions, AWS CLI availability, and native Docker/socket access without changing state.
# Fail on missing or conflicting prerequisites so operators do not mistake stack
# creation for a ready host; this does not prove credentials or factory execution.
set -euo pipefail
volume='@DATA_VOLUME_ID@'
trap 'status=$?; if [ "$status" -ne 0 ]; then echo "Host readiness failed at line $LINENO; inspect the check and host state" >&2; fi' EXIT
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
test "$(id -u)" = 0
test "$(uname -s):$(uname -m)" = Linux:aarch64
. /etc/os-release
test "$ID:$VERSION_ID" = ubuntu:24.04
mountpoint -q /srv/software-factory
device=$(findmnt -no SOURCE --mountpoint /srv/software-factory)
test "$(lsblk -dn -o SERIAL "$device" | tr -d ' -')" = "$(printf '%s' "$volume" | tr -d '-')"
test "$(findmnt -no FSTYPE --mountpoint /srv/software-factory)" = ext4
for mapping in home:/home/factory docker:/var/lib/docker containerd:/var/lib/containerd; do
  name=$(printf '%s' "$mapping" | cut -d: -f1)
  target=$(printf '%s' "$mapping" | cut -d: -f2)
  mountpoint -q "$target"
  test /srv/software-factory/"$name" -ef "$target"
done
test "$(id -u factory):$(id -g factory)" = 2000:2000
test "$(getent passwd factory | cut -d: -f6)" = /home/factory
test "$(stat -c '%u:%g:%a' /home/factory)" = 2000:2000:700
# Run checks with a clean factory environment and bounded local-engine calls, never administrator credentials.
as_factory() {
  timeout 30s runuser -u factory -- env -i HOME=/home/factory USER=factory LOGNAME=factory LANG=C.UTF-8 PATH=/usr/bin:/bin "$@"
}
as_factory sh -ec 'test -r "$HOME"; test -w "$HOME"; test -x "$HOME"'
as_factory aws --version >/dev/null
test -x /usr/bin/sudo
if as_factory sudo -n /bin/sh -c 'exit 0' >/dev/null 2>&1; then
  echo 'factory must not have general passwordless host sudo' >&2; exit 1
else test "$?" = 1; fi
test -S /var/run/docker.sock
mode=$(stat -c %a /var/run/docker.sock)
(( (8#$mode & 2) == 0 ))
case "$(as_factory docker --host unix:///var/run/docker.sock info --format '{{.OSType}}/{{.Architecture}}')" in
  linux/aarch64|linux/arm64) ;;
  *) echo 'factory requires native local Linux ARM64 Docker access' >&2; exit 1;;
esac
printf '%s\n' 'Factory host ready; credentials and image selection remain manual. Factory execution has not been started by this check.'
