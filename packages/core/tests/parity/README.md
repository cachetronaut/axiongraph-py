---
status: draft
updated: 2026-06-03
description: Cross-language parity fixtures for the graph-events core reducer — the shared contract both the TypeScript and Python cores must satisfy.
keywords: [parity, fixtures, reducer, canonical-json, cross-language, graph-events]
---

# Parity fixtures

Language-neutral golden cases that pin the deterministic reducer (spec D5, D10). The
TypeScript runner is `../parity.test.ts`; the Python mirror reads these same files.

## Layout

```text
parity/<case>/
  events.json     ordered GraphEvent[] — the input log (arrival order may be shuffled)
  state.json      the expected GraphState in serialized form (see below)
  manifest.json   optional — selects a non-default operation
```

`events.json` is always an array of events; the `runId` is taken from the first event.

`state.json` is the expected state as `{ runId, seq, nodes: NodePayload[], edges: EdgePayload[] }`.
Both sides rebuild a `GraphState` from it and compare through `canonicalize`, so the file
can stay human-readable — formatting and key order do not matter, only the canonical fold.

## Operations

| `manifest.op` | What the runner does | Compares against |
| --- | --- | --- |
| absent / `reduce` | `canonicalize(reduceAll(runId, events))` | `state.json` |
| `subgraph` | fold, then `subgraph(state, n => keepNodeKinds.has(n.kind))` | `state.json` |
| `validate` | event ids rejected by `validate(event, vocab)` | `manifest.rejected` |

## Required coverage

Per the spec, the set must cover: create-then-update merges (D6), out-of-order and
duplicate `seq` idempotency (D3), unknown-id updates dropped (D6), vocabulary rejection
(D2), and `subgraph` derivation. The runner asserts these case names are present.

All fixtures are synthetic and reveal nothing about any application.
