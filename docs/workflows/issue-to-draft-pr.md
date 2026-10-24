# Labeled issue → validated draft PR (US-01 / US-02 / US-03)

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
11. **Sandbox runs `./scripts/verify`.** After a completed check fails, Pi receives
    its stdout/stderr plus the unchanged task snapshot and repairs the same workspace.
    The runner re-verifies with the same command, allowing at most three repairs
    after the initial implementation and stopping at the first passing check.
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
- One 15-minute issue-run deadline covers setup, implementation, all repairs and
  verification, and publication. It never resets between attempts. Cleanup and failure reporting are attempted even after expiry.
- Passing verification without changes fails with `no changes produced`; no PR
  is created.
- Three unsuccessful repairs fail the issue run without a PR and retain diagnostics.
  Missing scripts, setup/provider errors, and sandbox/publication failures are not
  treated as completed verification failures that authorize another repair.
- US-02 live recovery-to-PR acceptance passed: issue 9 → draft PR 10 after one
  formatting-check failure and one repair, with independent CI green. See the
  [recorded acceptance](../../README.md#verification-beyond-unit-tests).
- Failure or interruption does not automatically retry or resume work. The
  operator must explicitly reapply the label and resolve any blocking remote
  branch. US-03 live acceptance passed: issue 13 was interrupted, stayed idle
  across restart, then explicit manual requeue produced draft PR 14 with independent
  CI green. See the [completion evidence](../slices/current-slice.md).
- The factory does not merge or implement review feedback. Passing verification
  does not guarantee requirement fulfillment; human review remains required.

## Manual requeue

1. Inspect the failed run's issue status and private diagnostics. After a hard
   crash, stop/remove any leftover run-owned containers before starting the single
   runner; restart alone does not requeue the issue.
2. Check `factory/issue-<number>`. A matching open PR is preserved and linked,
   not executed again. If the remote branch exists without an open PR, inspect
   and delete it yourself before reapplying the trigger; the runner never
   overwrites it. A closed PR does not bypass this check.
3. Edit the issue title/body if needed, then explicitly reapply `agent:implement`.
   A skip consumes the trigger too; branch cleanup after a skip requires another
   label reapplication.
4. The next poll repeats duplicate/branch checks and, if clear, captures a fresh
   snapshot and default-branch workspace with a new 900-second budget and up to
   three repairs. It does not resume the previous workspace or Pi session, and
   leaves earlier failed workspaces/logs intact until operator deletion.

All explicit stories are complete; no next story is defined in `SPEC.md`.

## References

- [Product specification](../../SPEC.md)
- [Non-HTTP contracts](../contracts.md)
- [Current slice and acceptance evidence](../slices/current-slice.md)
