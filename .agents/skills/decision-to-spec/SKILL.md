---
name: decision-to-spec
description: >
  Turn a repo-root DECISIONS.md into a concise repo-root SPEC.md using the
  standard product spec template. Use after grill-me or any accepted decision
  pack is complete enough for spec generation.
---

# Decision to Spec

## Overview

Use this skill to package locked decisions into a concise `SPEC.md` that later
planning and implementation skills can consume as a story backlog.

## Preconditions

Confirm all of the following before writing `SPEC.md`:

- repo-root `DECISIONS.md` exists
- `DECISIONS.md` marks spec generation as ready, or the user explicitly directs
  you to proceed anyway
- the repo does not have a conflicting established `SPEC.md` convention that
  you cannot safely infer

Stop and ask for clarification if `DECISIONS.md` is still materially ambiguous.

## Workflow

### 1. Read the decisions pack

- Read repo-root `DECISIONS.md` completely.
- Resolve the product summary, goals, actors, boundaries, business rules, and
  remaining open questions from that file.

### 2. Validate readiness

- If `DECISIONS.md` is not ready for spec generation and the user has not
  explicitly overridden that gate, stop and report the blocking ambiguity.
- Do not silently resolve open product decisions during spec generation.

### 3. Write exactly one `SPEC.md`

- Create or replace repo-root `SPEC.md`.
- Follow [references/spec-template.md](references/spec-template.md) exactly.
- Keep `SPEC.md` concise, user-facing, and backlog-oriented.
- Convert locked decisions into explicit, stable `US-xx` user stories and a stable lowercase hyphenated Spec ID. Preserve existing IDs when revising a spec; ask the operator if identity is unclear.
- Record explicit `Depends on` story IDs or `None.` for each story. Do not infer dependency edges; ask if a prerequisite is unclear.
- Derive story order from dependency order, not arbitrary grouping.
- Size every story as a thin vertical slice: one independently demonstrable
  user outcome. Include UI, API, persistence, and tests when that outcome
  requires them; never split a story by technical layer.
- Each story must state exactly one primary actor, trigger, happy-path action,
  visible outcome, and authoritative state transition.
- Split stories when they contain distinct user actions or outcomes.
- Keep required validation, authorization, error handling, and accessibility in
  the story they protect. Do not defer trust-boundary correctness.
- Put deferred work into ordered follow-up stories when it adds another action,
  outcome, integration, bulk flow, admin flow, or configuration path.
- Carry unresolved items into `## Open Questions` instead of guessing.
- Include a short source note pointing back to `DECISIONS.md`.

### 4. Apply the final sizing gate

Before writing `SPEC.md`, verify every story can be demonstrated by one focused
end-to-end test: one actor completes one action and observes one outcome. Split
any story that cannot meet this gate.

### 5. Stop and hand off

- Stop after writing `SPEC.md`.
- Hand off to `$spec-to-tickets` for a local reviewable plan; define contracts first when interfaces need to be locked.

## Rules

- Do not invent new business decisions.
- Do not write additional planning files.
- Do not create contracts.
- If a needed story or boundary remains ambiguous, reflect that in
  `## Open Questions` rather than silently deciding it.
