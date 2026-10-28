#!/bin/bash
# Start the selected local runner as factory with private retained logs and minimal
# persistent mounts. The runner validates TOML/selection; never pull or repair.
# Existing runner preflight remains authoritative for successful startup.
set -euo pipefail
umask 077
unset DOCKER_CONTEXT DOCKER_HOST
export PATH=/usr/sbin:/usr/bin:/sbin:/bin

test "$(id -u):$(id -g)" = 2000:2000
cidfile="${RUNTIME_DIRECTORY:?missing systemd runtime directory}/runner.cid"
state="$HOME/.config/software-factory"
logs="$HOME/.local/state/software-factory"
mkdir -p "$logs"
work=$(mktemp -d "$logs/start-XXXXXXXX")
printf 'Private startup/progress log: %s/runner.log\n' "$work" >&2
exec >> "$work/runner.log" 2>&1
trap 'echo "Factory start/exit failed; inspect this private log and retained run diagnostics" >&2' ERR

for image in "${RUNNER_IMAGE:?missing selected runner}" "${AGENT_IMAGE:?missing selected agent}"; do
  [[ "$image" =~ ^172318459814[.]dkr[.]ecr[.]eu-central-1[.]amazonaws[.]com/software-factory-(runner|agent)@sha256:[a-f0-9]{64}$ ]]
  platform=$(docker --host unix:///var/run/docker.sock image inspect --format '{{.Os}}/{{.Architecture}}' "$image")
  test "$platform" = linux/arm64
done
containers=$(docker --host unix:///var/run/docker.sock ps --quiet --filter 'name=^/(software-factory|factory-.*)$')
test -z "$containers"
if pgrep -u 2000 -f '[p]ython.*-m software_factory' >/dev/null; then
  echo 'Existing native runner requires inspection' >&2; exit 1
else test "$?" = 1; fi

mkdir -p /home/factory/artifacts
test -d "$HOME/.pi/agent"
socket_gid=$(stat -c %g /var/run/docker.sock)
# Foreground attachment preserves exit status; systemd stops the container, allowing cleanup before exit.
docker --host unix:///var/run/docker.sock run --rm --name software-factory --cidfile "$cidfile" \
  --pull=never --platform linux/arm64 --user 2000:2000 --group-add "$socket_gid" \
  --env "AGENT_IMAGE=$AGENT_IMAGE" --log-driver none --env DOCKER_HOST=unix:///var/run/docker.sock \
  --mount type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock \
  --mount type=bind,src=/home/factory/artifacts,dst=/home/factory/artifacts \
  --mount "type=bind,src=$state,dst=/home/factory/.config/software-factory,readonly" \
  --mount "type=bind,src=$HOME/.pi/agent,dst=/home/factory/.pi/agent" \
  "$RUNNER_IMAGE" --config /home/factory/.config/software-factory/factory.toml 2>&1 |
  while IFS= read -r record; do
    printf '%s\n' "$record"
    if [[ "$record" == *'"event": "runner_polling"'* ]]; then systemd-notify --ready; fi
  done
