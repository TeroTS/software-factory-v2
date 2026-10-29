---
name: spec-to-tickets
description: Turn a target repository's SPEC.md into a local, reviewable JSON ticket plan without publishing or queuing issues.
---

# Spec to Tickets

## Preconditions

- Read the target `SPEC.md`, `DECISIONS.md` when needed to resolve its meaning, and this factory's `docs/contracts.md` Contract 1 completely.
- Identify the target GitHub.com `owner/repository`, spec path and output path with the operator; do not assume the factory repository is the target.
- Require a stable Spec ID, unique stable `US-xx` IDs, and an explicit `Depends on` declaration for every story. Missing or ambiguous identity, scope, criteria, verification or dependencies requires clarification or spec revision, not invention.
- Each story must describe one actor, action and observable outcome that one focused end-to-end test can demonstrate. Flag oversized or ambiguous stories for spec revision; never split or silently change them.

## Generate

1. Read all stories in spec order. Map each to exactly one plan entry: preserve its ID, title, slice boundary as scope, acceptance criteria and explicitly declared dependency IDs. Extract verification instructions from the spec; if they are insufficient, ask the operator rather than inventing them.
2. Record the target repository and repository-relative POSIX spec path. Use the full lowercase commit ID only when the spec content exactly matches that committed file in the target checkout; otherwise set `source.commit` to `null` and tell the operator publication requires a committed source. Do not run target setup or other repository code.
3. Write one UTF-8 JSON file with exactly Contract 1's fields and types. Preserve story and list order. The JSON file, not this conversation, is the authoritative review artifact. Do not overwrite an existing file without the operator's permission.
4. From this factory's Python environment, run `python -m software_factory.planning validate --plan PLAN`, passing the selected path as a separate argument. Fix validation errors without inventing missing decisions. Review every story and dependency against the spec before reporting the artifact ready.
5. Report the path, any draft provenance, and stories requiring spec revision. Stop: do not call GitHub write commands, publish issues, or apply labels. Publication is a separate explicitly requested action.
