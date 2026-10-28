#!/bin/bash
# Finalize only a successfully baked disposable builder: reject private/retained
# state, clear cloned identities, then power off for explicit operator AMI capture.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 077
test "$(id -u)" = 0
test -f /run/factory-ami-builder
test ! -e /etc/software-factory/volume-id
for directory in /srv/software-factory /home/factory /var/lib/docker /var/lib/containerd /root/.aws /root/.docker /root/.pi; do
  if mountpoint -q "$directory"; then echo 'refusing capture with mounted factory state' >&2; exit 1; fi
  if test -e "$directory"; then
    test ! -L "$directory"
    test -z "$(find "$directory" -mindepth 1 -maxdepth 1 -print -quit)"
  fi
done
cloud-init clean --logs --machine-id --seed
systemctl stop snap.amazon-ssm-agent.amazon-ssm-agent.service
rm -rf -- /var/lib/amazon/ssm /var/snap/amazon-ssm-agent/common /var/log/amazon/ssm
rm -f -- /etc/ssh/ssh_host_*
touch /etc/software-factory/capture-ready
systemctl poweroff
