"""A live smoke test for the Convex adapter against a real deployment.

Gated on ``CONVEX_URL`` — the whole module is skipped unless it is set, so the default test run
needs neither a deployment nor the ``convex`` client installed. There is no offline harness on the
Python side (the component lives in the TypeScript package; ``convex-test`` is JS-only), so unlike
Postgres this isn't run in CI by default — point ``CONVEX_URL`` at a deployment that has the
axiongraph component installed and the exposed functions deployed (your ``npx convex dev``).

Cross-language note to verify live: the component's ``seq`` column is ``v.number()`` (float64),
while Python ints map to Convex int64 — confirm appends/reads round-trip cleanly through the wire.

The store API is async; the test drives it with ``asyncio.run`` to avoid a pytest-asyncio dep."""

from __future__ import annotations

import asyncio
import os
from typing import cast

import pytest

if not os.environ.get("CONVEX_URL"):
    pytest.skip(
        "set CONVEX_URL to run the Convex live smoke test",
        allow_module_level=True,
    )

# Narrowed to ``str``: the skip above aborts collection when it is unset.
CONVEX_URL = cast(str, os.environ.get("CONVEX_URL"))

# Imported only once the gate passes, so a default run never needs the convex client.
from axiongraph_core import GraphEvent  # noqa: E402
from axiongraph_store_convex import ConvexStore  # noqa: E402
from convex import ConvexClient  # noqa: E402


def test_round_trips_events_through_the_deployed_component() -> None:
    run_id = f"run_live_{os.getpid()}"
    event: GraphEvent = {
        "id": f"{run_id}-e1",
        "runId": run_id,
        "seq": 1,
        "ts": "2026-06-03T00:00:00.000Z",
        "type": "node_created",
        "node": {"id": "a", "kind": "agent", "label": "Live"},
    }

    async def scenario() -> None:
        store = ConvexStore(ConvexClient(CONVEX_URL))
        await store.append([event])
        await store.append([event])  # idempotent on (runId, seq)
        state = await store.snapshot(run_id)
        assert state.nodes["a"]["label"] == "Live"
        assert state.seq == 1

    asyncio.run(scenario())
