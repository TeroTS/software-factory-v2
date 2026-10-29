---
name: grill-me
description: >
  Interview the user one decision at a time to remove ambiguity from a plan or
  design, then write a repo-root DECISIONS.md using the canonical template. Use
  when the user wants to be grilled, stress-test a plan, or lock product or
  design decisions before spec creation.
---

# Grill Me

## Overview

Use this skill to turn ambiguous product or technical intent into a
decision-complete planning record. Explore discoverable facts first, ask one
material question at a time, and finish by creating or replacing repo-root
`DECISIONS.md`.

## Workflow

### 1. Ground in discoverable facts

- Explore the repo, docs, configs, and code before asking about facts the
  environment can answer.
- Ask only preference or tradeoff questions that materially change the future
  spec or implementation plan.

### 2. Interrogate one decision at a time

- Ask one question per turn.
- Provide a recommended answer with each question.
- Keep going until goals, success criteria, actors, scope boundaries, business
  rules, data ownership, interface expectations, operational constraints,
  assumptions, and open questions are explicit.

### 3. Write `DECISIONS.md`

- When questioning is complete enough, create or replace repo-root
  `DECISIONS.md`.
- Follow
  [references/decisions-template.md](./references/decisions-template.md)
  exactly.
- Group locked decisions by area instead of preserving chat chronology.
- Record unresolved items in `## Open Questions`.
- In `## Ready for Spec Generation`, say explicitly whether
  `$decision-to-spec` can proceed without inventing policy.

### 4. Handoff

- If `DECISIONS.md` is ready for spec generation, the next step is
  `$decision-to-spec`.

## Rules

- Ask questions one at a time.
- If a question can be answered by exploring the codebase, explore instead.
- Do not write `SPEC.md`.
- Do not create slice notes.
- Do not jump to implementation planning while material product or design
  ambiguity remains.
