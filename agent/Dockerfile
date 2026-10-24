# Build the credential-free native ARM64 shared baseline; the operator builds it before runner startup.
FROM node:22.19.0-bookworm-slim@sha256:4a4884e8a44826194dff92ba316264f392056cbe243dcc9fd3551e71cea02b90 AS node
FROM docker:28.4.0-cli@sha256:6a73c9433f2ba4279815be1e60f5739288b939dda1e48151d8c393537802de37 AS docker
FROM python:3.14.3-slim-bookworm@sha256:f21c0d5a44c56805654c15abccc1b2fd576c8d93aca0a3f74b4aba2dc92510e2

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
COPY --from=docker /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker /usr/local/libexec/docker/cli-plugins /usr/local/libexec/docker/cli-plugins

# Freeze Debian tool/dependency versions to one signed snapshot instead of floating apt repositories.
RUN printf '%s\n' \
      'Types: deb' \
      'URIs: http://snapshot.debian.org/archive/debian/20260301T000000Z/' \
      'Suites: bookworm bookworm-updates' \
      'Components: main' \
      'Check-Valid-Until: no' \
      '' \
      'Types: deb' \
      'URIs: http://snapshot.debian.org/archive/debian-security/20260301T000000Z/' \
      'Suites: bookworm-security' \
      'Components: main' \
      'Check-Valid-Until: no' > /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
      bash build-essential ca-certificates curl git make tar unzip \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && python -m pip install --no-cache-dir uv==0.5.13 \
    && npm install --global --ignore-scripts @earendil-works/pi-coding-agent@1.3.0 \
    && npm cache clean --force

# Allow explicit noninteractive system installs; ordinary issue commands use the host UID/GID.
RUN apt-get update \
    && apt-get install -y --no-install-recommends sudo \
    && printf '%s\n' 'Defaults always_set_home' 'ALL ALL=(root) NOPASSWD: ALL' > /etc/sudoers.d/factory \
    && chmod 0440 /etc/sudoers.d/factory \
    && visudo -cf /etc/sudoers.d/factory \
    && rm -rf /var/lib/apt/lists/*

ENV UV_LINK_MODE=copy
WORKDIR /tmp
USER root
