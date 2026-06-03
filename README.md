# AxionGraph (Python)

<p align="center">
  <img src="https://raw.githubusercontent.com/cachetronaut/axiongraph-py/main/docs/assets/axiongraph.png" alt="AxionGraph logo" height="500px" />
</p>


> Invisible events. Replayable graphs.

AxionGraph is an append-only event model and deterministic reducer for execution graphs.
It records graph events from agents, tools, workflows, and connectors, then folds them into
portable graph state for storage, replay, testing, and visualization.

This is the Python mirror of [`axiongraph` on npm](https://www.npmjs.com/package/axiongraph);
the two cores are kept in lockstep by shared cross-language parity fixtures.

```python
from axiongraph import reduce_all

events = [
    {"id": "evt_01", "runId": "run_01", "seq": 1, "ts": "2026-06-02T12:00:00.000Z",
     "type": "node_created", "node": {"id": "agent_research", "kind": "agent", "label": "Research Agent"}},
    {"id": "evt_02", "runId": "run_01", "seq": 2, "ts": "2026-06-02T12:00:01.000Z",
     "type": "node_created", "node": {"id": "tool_web", "kind": "tool", "label": "Web Search"}},
    {"id": "evt_03", "runId": "run_01", "seq": 3, "ts": "2026-06-02T12:00:02.000Z",
     "type": "edge_created",
     "edge": {"id": "edge_01", "kind": "called_tool", "from": "agent_research", "to": "tool_web", "status": "completed"}},
]

state = reduce_all("run_01", events)
print(len(state.nodes))  # 2
print(len(state.edges))  # 1
```

## Core ideas

- Append-only events are the source of truth; graph state is derived by folding them.
- The reducer is pure and deterministic — identical event logs fold to byte-identical state.
- A monotonic `seq` per run defines order; wall-clock `ts` is advisory.
- Node/edge `kind` is an open taxonomy; supply a `GraphVocabulary` to reject unknown kinds.
- Storage is a port (`GraphStore`); rendering and realtime transport are consumer concerns.
- Event/payload shapes use the same wire keys as the TypeScript package (`runId`, `from`) so
  the same events flow across both runtimes.

## One package, opt-in extras

AxionGraph ships as a single `axiongraph` distribution. The core API is the top-level import;
optional backends are installed as extras (`pip install axiongraph[...]`). The local stores
need no extra — `sqlite3` is in the standard library.

| Import | Description | Extra |
| --- | --- | --- |
| `axiongraph` | Event model, deterministic reducer, canonicalizer, vocabulary machinery, and the `GraphStore` port. | — |
| `axiongraph.store_local` | Zero-service reference adapters: an in-memory store and a `sqlite3`-backed durable store. | — |
| `axiongraph.store_postgres` | Durable `PostgresStore` backed by `psycopg`: a `jsonb` event log keyed on `(runId, seq)`, idempotent appends, live-fold snapshots. | `postgres` |

```sh
pip install 'axiongraph[postgres]'   # pulls in psycopg
```

## Install

```sh
pip install axiongraph        # or: uv add axiongraph
```

## Storing and replaying events

```python
from axiongraph.store_local import SqliteStore  # or InMemoryStore

store = SqliteStore("./run.db")        # ":memory:" by default
await store.append(events)             # idempotent on (runId, seq)
state = await store.snapshot("run_01")
```

Both `InMemoryStore` and `SqliteStore` satisfy the same `GraphStore` protocol and are
interchangeable; any future adapter that passes the shared contract suite drops in the same way.

## Development

Python 3.11+ and [uv](https://docs.astral.sh/uv/). The repo is an internal package set
(`packages/core`, `packages/store-local`, `packages/store-postgres`, plus a dev-only
`packages/testkit` shared contract suite) assembled by hatchling into the one `axiongraph`
distribution.

```sh
uv sync --dev
uv run ruff check . && uv run ruff format --check .
uv run ty check
uv run pytest
```

The Postgres contract suite is gated on `AXIONGRAPH_TEST_POSTGRES_URL`; it is skipped unless
set, and CI runs it against a `postgres:16` service.

## Status

Early development. The reducer and reference stores are implemented and pass the same
parity fixtures as the TypeScript package.

## License

MIT
