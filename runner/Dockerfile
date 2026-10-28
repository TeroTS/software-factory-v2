# Package only the host runner; agent tools/instructions remain independently owned by agent/Dockerfile.
FROM python:3.14.3-slim-bookworm@sha256:f21c0d5a44c56805654c15abccc1b2fd576c8d93aca0a3f74b4aba2dc92510e2 AS python
FROM node:22.19.0-bookworm-slim@sha256:4a4884e8a44826194dff92ba316264f392056cbe243dcc9fd3551e71cea02b90 AS node
FROM docker:28.4.0-cli@sha256:6a73c9433f2ba4279815be1e60f5739288b939dda1e48151d8c393537802de37 AS docker
FROM ubuntu:24.04@sha256:19cad59657037cffa0ac9a48107019b768900ff1071140965827513ac866bd5e

COPY --from=python /usr/local /usr/local
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
COPY --from=docker /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker /usr/local/libexec/docker/cli-plugins /usr/local/libexec/docker/cli-plugins
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      ca-certificates=20260816ubuntu0.24.04.1 curl=8.5.0-2ubuntu10.16 \
      git=1:2.43.0-1ubuntu7.4 openssl=3.0.13-0ubuntu3.16 \
      libexpat1 libffi8 libbz2-1.0 liblzma5 libsqlite3-0 libreadline8t64 \
    && ldconfig \
    && ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && npm install --global --ignore-scripts @earendil-works/pi-coding-agent@1.3.0 \
    && npm cache clean --force \
    && curl --fail --location --output /tmp/gh.deb \
      https://github.com/cli/cli/releases/download/v2.103.3/gh_2.103.3_linux_arm64.deb \
    && echo 'cac3ff84b60b68e64cca69f31f303210c26320361cc3286b773655d4226b7b06  /tmp/gh.deb' | sha256sum --check \
    && dpkg -i /tmp/gh.deb \
    && rm /tmp/gh.deb \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 2000 factory \
    && useradd --uid 2000 --gid 2000 --home-dir /home/factory --shell /bin/bash factory \
    && install -d -m 0700 -o factory -g factory /home/factory

COPY src/software_factory /opt/software-factory/src/software_factory
ENV HOME=/home/factory PYTHONPATH=/opt/software-factory/src PYTHONDONTWRITEBYTECODE=1
WORKDIR /home/factory
USER factory:factory
ENTRYPOINT ["python", "-m", "software_factory"]
