#!/bin/bash
# Stop only this service invocation's recorded container, including failed startup;
# give existing interruption/cleanup time to finish and expose stop errors.
set -euo pipefail
cidfile="${RUNTIME_DIRECTORY:?}/runner.cid"
if test -s "$cidfile"; then
  cid=$(<"$cidfile")
  [[ "$cid" =~ ^[a-f0-9]{64}$ ]]
  docker --host unix:///var/run/docker.sock stop --time 120 "$cid"
  rm -f -- "$cidfile"
fi
