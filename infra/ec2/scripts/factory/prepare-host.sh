#!/bin/bash
# Prepare a baked host using the stack-owned volume setting; mount retained state
# before unmasking Docker. Never install packages, enroll credentials or start the factory.
set -euo pipefail
set -E
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
trap 'echo "EC2 host preparation failed at line $LINENO; inspect cloud-init logs" >&2' ERR

# Reject unsupported hosts or already-active work before preparing storage.
validate_host() {
  test "$(id -u)" = 0
  test "$(uname -s):$(uname -m)" = Linux:aarch64
  . /etc/os-release
  test "$ID:$VERSION_ID" = ubuntu:24.04
  for service in software-factory docker containerd; do
    if systemctl is-active --quiet "$service"; then echo "refusing preparation with active $service" >&2; exit 1; fi
  done
}
# Verify baked factory identity rather than creating accounts or repairing retained permissions at boot.
validate_identity() {
  test "$(id -u factory):$(id -g factory)" = 2000:2000
  test "$(getent passwd factory | cut -d: -f6)" = /home/factory
}
# Use only the CloudFormation-selected volume; any storage/start/readiness error prevents a ready report.
prepare_host() {
  validate_host
  validate_identity
  volume=$(</etc/software-factory/volume-id)
  /usr/local/sbin/factory-prepare-storage "$volume"
  systemctl unmask docker.service docker.socket containerd.service
  systemd-analyze verify /etc/systemd/system/software-factory.service
  systemctl enable --now docker
  /usr/local/sbin/factory-host-check
}

if [[ ${BASH_SOURCE[0]:-} == "$0" ]]; then prepare_host; fi
