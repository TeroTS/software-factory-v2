#!/bin/bash
# Install only generic host prerequisites on a disposable Ubuntu ARM64 builder;
# mask engines before package installation, record provenance and leave capture explicit.
set -euo pipefail
umask 077
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export DEBIAN_FRONTEND=noninteractive

# Reject unsupported hosts or active execution before installing anything.
validate_host() {
  test "$(id -u)" = 0
  test "$(uname -s):$(uname -m)" = Linux:aarch64
  . /etc/os-release
  test "$ID:$VERSION_ID" = ubuntu:24.04
  for service in software-factory docker containerd; do
    if systemctl is-active --quiet "$service"; then echo "refusing bake with active $service" >&2; exit 1; fi
  done
}
# Create fixed factory identity without moving home data, renumbering accounts or granting host sudo.
ensure_account() {
  local key entry name password uid gid rest home shell
  for key in factory 2000; do
    if entry=$(getent passwd "$key"); then
      IFS=: read -r name password uid gid rest home shell <<< "$entry"
      test "$name:$uid:$gid:$home" = factory:2000:2000:/home/factory
    else test "$?" = 2; fi
    if entry=$(getent group "$key"); then
      IFS=: read -r name password gid rest <<< "$entry"
      test "$name:$gid" = factory:2000
    else test "$?" = 2; fi
  done
  if ! getent group factory >/dev/null; then groupadd --gid 2000 factory; fi
  if ! getent passwd factory >/dev/null; then
    useradd --uid 2000 --gid 2000 --no-create-home --home-dir /home/factory --shell /bin/bash factory
  fi
}
# Install signed Docker packages and AWS's approved HTTPS installer without starting engines; discard temporary files.
install_docker() (
  work=$(mktemp -d)
  trap 'rm -rf -- "$work"' EXIT
  chmod 0755 "$work"
  for suite in noble noble-updates noble-security; do
    printf 'deb [arch=arm64 signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] http://ports.ubuntu.com/ubuntu-ports %s main\n' "$suite"
  done > "$work/sources.list"
  chmod 0644 "$work/sources.list"
  local options=(-o "Dir::Etc::sourcelist=$work/sources.list" -o Dir::Etc::sourceparts=- -o APT::Update::Error-Mode=any)
  apt-get "${options[@]}" update
  apt-get "${options[@]}" install --yes --no-remove --no-install-recommends sudo curl ca-certificates gnupg unzip
  for destination in /usr/local/aws-cli /usr/bin/aws /usr/bin/aws_completer; do
    if test -e "$destination" || test -L "$destination"; then
      echo 'refusing to overwrite an existing AWS CLI path; inspect the builder' >&2; exit 1
    fi
  done
  curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --connect-timeout 15 --max-time 180 --output "$work/awscliv2.zip" https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip
  (
    umask 022
    unzip -q "$work/awscliv2.zip" -d "$work"
    "$work/aws/install" --install-dir /usr/local/aws-cli --bin-dir /usr/bin
  )
  curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --connect-timeout 15 --max-time 90 --output "$work/docker.asc" https://download.docker.com/linux/ubuntu/gpg
  printf '%s  %s\n' 1500c1f56fa9e26b9b8f42452a553675796ade0807cdce11975eb98170b3a570 "$work/docker.asc" | sha256sum --check --status
  install -d -m 0755 /etc/apt/keyrings /etc/apt/sources.list.d
  install -m 0644 "$work/docker.asc" /etc/apt/keyrings/docker.asc
  printf '%s\n' 'deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable' > /etc/apt/sources.list.d/factory-docker.list
  chmod 0644 /etc/apt/sources.list.d/factory-docker.list
  cat /etc/apt/sources.list.d/factory-docker.list >> "$work/sources.list"
  apt-get "${options[@]}" update
  apt-get "${options[@]}" install --yes --no-remove --no-install-recommends docker-ce docker-ce-cli containerd.io
  usermod --append --groups docker factory
)
# Bake guarded tools/files and public provenance only; failures never mark the builder ready for finalization.
bake_host() {
  validate_host
  systemctl enable --now snap.amazon-ssm-agent.amazon-ssm-agent.service
  : "${FACTORY_PARENT_AMI:?}" "${FACTORY_SOURCE_REVISION:?}"
  test ! -e /usr/sbin/policy-rc.d; test ! -L /usr/sbin/policy-rc.d
  systemctl mask docker.service docker.socket containerd.service
  source /usr/local/sbin/factory-prepare-storage
  install_storage_guards
  printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
  chmod 0755 /usr/sbin/policy-rc.d
  trap 'rm -f -- /usr/sbin/policy-rc.d' EXIT
  ensure_account
  install_docker
  install -d -m 0755 /etc/software-factory
  {
    printf 'parent_ami=%s\nsource_revision=%s\n' "$FACTORY_PARENT_AMI" "$FACTORY_SOURCE_REVISION"
    dpkg-query -W docker-ce docker-ce-cli containerd.io
    aws --version
  } > /etc/software-factory/image-info
  chmod 0644 /etc/software-factory/image-info
  touch /run/factory-ami-builder
  echo 'AMI bake complete; inspect provenance and explicitly finalize before capture.'
}

if [[ ${BASH_SOURCE[0]:-} == "$0" ]]; then bake_host; fi
