 1. Local runner polls for agent:implement issues and checks for an existing factory PR/branch.
 2. It claims the issue, snapshots its title/body, creates a fresh workspace from the target’s
    default branch, and starts the shared agent container with that workspace mounted.
 3. The runner executes ./scripts/setup inside the agent container. Setup must succeed before
    Pi starts.
 4. Pi implements the issue; the runner executes ./scripts/verify inside the same container.
 5. If verification fails, Pi gets the failure output and repairs the same workspace, followed
    by another verification run—up to three repairs after the initial implementation, meaning
    at most four verification runs.
 6. On success, the runner stops run-owned services/processes and cleans owned Docker resources
    before committing and publishing a draft PR. The workspace cannot be deleted before
    publication.
 7. On failure, it still attempts Docker cleanup, but retains the private workspace/logs for diagnosis.
