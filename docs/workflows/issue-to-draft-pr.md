# US-01: Labeled issue → validated draft PR

## Chronological steps

1. **Operator prepares the target repository:** setup/verify scripts, sandbox
   environment, credentials, and runner configuration.
2. **Operator starts the local runner.**
3. **Operator labels an issue** `agent:implement`.
4. **Local runner discovers the issue** during polling.
5. **Local runner checks for existing work:**
   - Matching open draft or non-draft PR → remove the label, comment with its
     link, and skip execution.
   - Existing factory branch without a matching open PR → remove the label,
     request manual branch cleanup, and skip execution.
6. **Local runner claims the issue:** removes the label and posts running status.
7. **Local runner snapshots the issue title/body** and creates a fresh workspace
   from the target repository's default branch.
8. **Local runner obtains Copilot-only credentials** and starts the isolated
   Compose sandbox.
9. **Sandbox runs `./scripts/setup`.** Both setup and verify entrypoints must
   exist and be executable.
10. **Pi coding agent implements the issue unattended**, using the snapshot and
    repository contents, without retrieving comments, attachments, or linked pages.
11. **Sandbox runs `./scripts/verify`.**
12. **Local runner stops and removes run-owned sandbox containers.**
13. **Local runner confirms changes exist** and commits them using trusted
    host-side Git.
14. **Local runner creates the remote factory branch** `factory/issue-<number>`
    without overwriting an existing branch.
15. **Local runner opens a draft PR** containing `Closes #<number>`.
16. **Local runner comments on the issue with the draft PR link** and deletes the
    successful local run directory.
17. **Independent CI runs; a human reviewer reviews and decides whether to merge.**
    CI may start as soon as the branch or PR is published; the runner does not
    wait for it before reporting publication success.

## Failure behavior and limits

- Failures stop normal progression, retain local diagnostics, and report failure
  where possible. Container cleanup is always attempted.
- One 15-minute issue-run deadline covers setup, implementation, verification,
  and publication. Cleanup and failure reporting are attempted even after expiry.
- Passing verification without changes fails with `no changes produced`; no PR
  is created.
- Verification failure currently fails the run immediately. Bounded repairs are
  deferred to US-02.
- Failure or interruption does not automatically retry or resume work. The
  operator must explicitly reapply the label and resolve any blocking remote
  branch. Successful manual-requeue acceptance remains US-03 work.
- The factory does not merge or implement review feedback. Passing verification
  does not guarantee requirement fulfillment; human review remains required.

## References

- [Product specification](../../SPEC.md)
- [Non-HTTP contracts](../contracts.md)
- [Current slice and acceptance evidence](../slices/current-slice.md)
