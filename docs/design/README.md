# PinSheet — Design Documentation

Design and architecture reference for PinSheet, living alongside the code under
`docs/design/`. Supplementary material: it does not ship in the app runtime — it
exists so a human or an LLM agent can quickly understand how the service works
before changing it. Reachable from the main [`README.md`](../../README.md) →
Documentation; the vendor-neutral agent entrypoint is
[`AGENT_GUIDE.md`](./AGENT_GUIDE.md).

## Design goals for these docs

- **LLM-agnostic.** Nothing here assumes a specific agent (Claude, GPT, Gemini,
  Cursor, local models, …). Conventions use the vendor-neutral `AGENTS.md`
  standard. If a specific tool needs an entrypoint file (e.g. `CLAUDE.md`), it
  should be a thin pointer to [`AGENT_GUIDE.md`](./AGENT_GUIDE.md), not a fork.
- **Diagrams over prose.** Flows are Mermaid sequence diagrams (render natively
  on GitHub, parse cleanly as text for any model).
- **Navigable by glob.** [`FILE_MAP.md`](./FILE_MAP.md) maps glob patterns to
  responsibilities so an agent can jump to the right file without reading the
  tree.
- **Source of truth stays in code.** These docs describe intent and structure;
  when they disagree with the code, the code wins — open an issue/PR here to
  reconcile.

## Contents

| Document | What it answers |
|----------|-----------------|
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | Stack, layers, request lifecycle, data model, the handicap engine, plugins |
| [`SEQUENCES.md`](./SEQUENCES.md) | Sequence diagrams for the core flows (round entry, edit + recompute cascade, handicap calc, score evaluation, auth, course create) |
| [`FILE_MAP.md`](./FILE_MAP.md) | Glob → responsibility map for fast navigation |
| [`AGENT_GUIDE.md`](./AGENT_GUIDE.md) | Conventions, invariants, gotchas, and how to run/verify — for any coding agent or new contributor |
| [`INVARIANTS.md`](./INVARIANTS.md) | Non-obvious rules the code depends on (break these and things silently corrupt) |

## Applies to

PinSheet `>= v0.8.1`. The application is a self-hosted Flask app (single-user
per instance, multi-user aware) that tracks golf rounds, scores, handicap
index (WHS-style), stats, matches, and challenges.

> Keep these docs in sync when the flows in `SEQUENCES.md` or the invariants in
> `INVARIANTS.md` change. Update them in the same PR as any behavioural change to
> round/score/handicap logic.
