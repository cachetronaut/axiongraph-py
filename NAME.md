# Name

**AxionGraph** (Python mirror)

> Invisible events. Replayable graphs.

The Python mirror of AxionGraph, published as a single `axiongraph` distribution on PyPI.
The working name during design was `graph-events`.

## Package and imports

One published distribution, `axiongraph`, with the core API at the top level and the stores
as a submodule — the PyPI-extras model (optional backends install as extras).

- `axiongraph` — event model, deterministic reducer, canonicalizer, vocabulary machinery,
  and the `GraphStore` port.
- `axiongraph.store_local` — zero-service reference adapters (`InMemoryStore`, `SqliteStore`).

Internally the repo assembles `axiongraph_core` and `axiongraph_store_local` (under
`packages/*`) into the one distribution via hatchling.

## Notes

- Repository directory is `axiongraph-py/`; the `-py` suffix distinguishes it from the
  TypeScript package `axiongraph-ts` (published as `axiongraph` on npm).
- Cross-language parity with the TypeScript core is enforced by the shared fixtures under
  `packages/core/tests/parity/`.
