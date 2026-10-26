# Factory implementation instructions

- Implement the issue without clarification questions. Use only the
  task snapshot and repository contents; do not retrieve
  issue comments, attachments, or linked pages.
- Apply both required factory skills included below: test-driven-development and
  Ponytail full. Use each skill's stated base directory for supporting references.
  Preserve target coding conventions, existing work, tests, and safety requirements.
  Report checks actually run and any blockers; never claim unobserved TDD evidence.
- Add meaningful tests. Do not publish, commit, or push; the host handles
  publication after verification.
- Run ordinary setup, builds, and tests as the factory account (UID/GID 2000:2000).
  Use explicit sudo -n only for system installs;
  never retry permission errors automatically as root.
- Keep service-private data in disposable run-owned volumes; workspace-writing
  services need compatible ownership.
  Cleanup will not repair workspace ownership or permissions.
- Use native linux/arm64 tools and images only; do not request emulation.
- Keep inherited COMPOSE_PROJECT_NAME for ordinary Compose commands. Label
  directly created containers, networks, and disposable volumes with
  software-factory.run-id=$FACTORY_RUN_ID.
  Do not prune, remove shared resources, or change Docker contexts.
- Use explicit service addresses: Compose DNS after joining its network, or
  published ports through the Docker host;
  sibling services do not share your localhost.
