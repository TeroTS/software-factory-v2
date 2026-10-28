#!/bin/bash
# Prepare the stack volume passed as $1, formatting only blank media and mounting
# retained factory home and Docker/containerd data before Docker can start.
# Persist mounts and service dependencies so state survives root-disk replacement;
# reject disk, filesystem, or mount conflicts rather than overwrite existing data.
set -euo pipefail

# Persist one expected mount entry; conflicting existing entries require operator inspection.
persist_mount() {
  local entry="$*" existing
  existing=$(awk -v target="$2" '$2 == target {print}' /etc/fstab)
  if [ -n "$existing" ] && [ "$existing" != "$entry" ]; then echo 'refusing conflicting fstab entry' >&2; exit 1; fi
  if [ -z "$existing" ]; then printf '%s\n' "$entry" >> /etc/fstab; fi
}

# Identify only the stack data volume, format only blank media, and mount persistent state before Docker.
prepare_storage() {
  volume=${1:?expected stack data volume ID}
  device=/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_$(printf '%s' "$volume" | tr -d '-')
  for attempt in $(seq 1 120); do [ ! -b "$device" ] || break; sleep 2; done
  test -b "$device"
  test "$(lsblk -dn -o SERIAL "$device" | tr -d ' -')" = "$(printf '%s' "$volume" | tr -d '-')"
  filesystem=$(lsblk -dn -o FSTYPE "$device")
  if [ -z "$filesystem" ]; then
    test "$(lsblk -n -o TYPE "$device")" = disk
    test -z "$(lsblk -nr -o MOUNTPOINT "$device")"
    wipefs --no-act --json "$device" | /usr/bin/python3 -c 'import json,sys; assert not json.load(sys.stdin)["signatures"], "refusing disk with existing signatures"'
    mkfs.ext4 -L factory-data "$device"
  elif [ "$filesystem" != ext4 ]; then
    echo 'refusing non-ext4 data volume' >&2; exit 1
  fi
  uuid=$(blkid -s UUID -o value "$device")
  test -n "$uuid"
  test ! -L /srv/software-factory
  mkdir -p /srv/software-factory
  if mountpoint -q /srv/software-factory; then
    test "$(findmnt -no UUID --mountpoint /srv/software-factory)" = "$uuid"
  else
    test -z "$(find /srv/software-factory -mindepth 1 -maxdepth 1 -print -quit)"
    mount "$device" /srv/software-factory
  fi
  persist_mount UUID=$uuid /srv/software-factory ext4 defaults,nofail,x-systemd.device-timeout=120s 0 2
  for mapping in home:/home/factory docker:/var/lib/docker containerd:/var/lib/containerd; do
    name=$(printf '%s' "$mapping" | cut -d: -f1)
    target=$(printf '%s' "$mapping" | cut -d: -f2)
    source=/srv/software-factory/$name
    test ! -L "$source"; test ! -L "$target"
    if [ ! -e "$source" ]; then
      if [ "$name" = home ]; then install -d -m 0700 -o 2000 -g 2000 "$source"; else mkdir "$source"; fi
    fi
    if [ "$name" = home ]; then test "$(stat -c '%u:%g' "$source")" = 2000:2000; fi
    mkdir -p "$target"
    if mountpoint -q "$target"; then test "$source" -ef "$target"; else
      test -z "$(find "$target" -mindepth 1 -maxdepth 1 -print -quit)"
      mount --bind "$source" "$target"
    fi
    persist_mount "$source" "$target" none bind,nofail,x-systemd.requires-mounts-for=/srv/software-factory 0 0
  done
  for service in docker containerd; do
    directory=/etc/systemd/system/$service.service.d
    mkdir -p "$directory"
    expected=$(printf '[Unit]\nRequiresMountsFor=/srv/software-factory /var/lib/docker /var/lib/containerd\n')
    file=$directory/factory-storage.conf
    if [ -e "$file" ]; then test ! -L "$file"; test "$(<"$file")" = "$expected"; else printf '%s\n' "$expected" > "$file"; fi
  done
  systemctl daemon-reload
}

if [[ ${BASH_SOURCE[0]:-} == "$0" ]]; then prepare_storage "$@"; fi
