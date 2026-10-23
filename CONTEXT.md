# Domain Vocabulary

## Canonical Terms

### Autonomous coding factory

The local system that turns labeled GitHub issues into implemented, validated draft PRs for human review.

### Operator

The person who prepares the target repository, runs the factory, applies trigger labels, and handles manual requeue and cleanup.

### Target repository

The single trusted GitHub repository configured for the factory, with prepared setup/verify commands and a sandbox environment.

### Issue

The GitHub work request attempted when labeled `agent:implement`. Its title and body are snapshotted at run start; comments, attachments, and linked pages are not task inputs.

### Local runner

The factory actor that polls for labeled issues, manages one issue run at a time, invokes the coding agent and verification, and publishes results.

### Issue run

One attempt to process an issue from claim to success or failure, including setup, initial implementation, and any repair attempts under one 15-minute deadline.

### Repair attempt

One agent repair followed by verification after a verification failure. An issue run permits up to three repair attempts after the initial implementation.

### Factory branch

The branch `factory/issue-<number>` used to publish an issue's changes and detect an existing factory PR. Existing remote branches are never overwritten or force-pushed.

### Draft PR

The factory's reviewable result: a draft GitHub pull request containing changes that passed repository verification and linking the issue with `Closes #<number>`. It is not automatically merged.

### Human reviewer

The person who evaluates the draft PR, requirement fulfillment, tests, and CI results and decides whether to merge.

### Manual requeue

The operator's explicit reapplication of `agent:implement` after failure or interruption. It requests a fresh issue run, not resumption of the previous agent session; remote branch cleanup may be required first.
