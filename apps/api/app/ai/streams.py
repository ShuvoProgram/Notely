"""Agent runs execute independently of the HTTP request that started them.

`POST /ai/chat` (and `/ai/approve`) prepare the run, then hand it to a background task that
publishes every event into a per-run channel. The response is only a *subscription* to that
channel, so:

  - a client that navigates to another conversation, reloads, or drops its connection does not
    stop the run (it keeps going and is persisted);
  - a client can re-attach with `GET /ai/runs/{id}/stream?after=<seq>` and get the missed
    events replayed, then the rest live, with no duplicates;
  - runs in different conversations share nothing but the process: each has its own task,
    DB session, agent context and LangGraph thread.

Every published event carries `run_id`, `thread_id` and a per-run `seq`, so clients can route
it to the right conversation and drop anything stale or already seen.

While a run's task is alive it refreshes a short-lived KV heartbeat. A run left `running` with
no heartbeat (process crash, deploy) is orphaned and gets closed as failed instead of blocking
its conversation forever.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from app.core.kv import kv
from app.core.logging import get_logger

log = get_logger(__name__)

HEARTBEAT_EVERY = 5.0
HEARTBEAT_TTL = 20
KEEPALIVE_EVERY = 15.0
# Finished channels stay replayable briefly so a client reconnecting right after the end still
# receives the tail (then it falls back to the persisted thread).
RETAIN_FINISHED = 120.0


def alive_key(run_id: uuid.UUID) -> str:
    return f"ai:run:alive:{run_id}"


class RunChannel:
    def __init__(self, run_id: uuid.UUID, thread_id: uuid.UUID, user_id: uuid.UUID) -> None:
        self.run_id = run_id
        self.thread_id = thread_id
        self.user_id = user_id
        self.events: list[dict[str, Any]] = []
        self.done = False
        self.finished_at: float | None = None
        self.task: asyncio.Task[None] | None = None
        self._changed = asyncio.Condition()

    async def publish(self, event: dict[str, Any]) -> None:
        async with self._changed:
            self.events.append(
                {
                    **event,
                    "run_id": str(self.run_id),
                    "thread_id": str(self.thread_id),
                    "seq": len(self.events),
                }
            )
            self._changed.notify_all()

    async def close(self) -> None:
        async with self._changed:
            self.done = True
            self.finished_at = time.monotonic()
            self._changed.notify_all()

    async def subscribe(self, after: int = -1) -> AsyncIterator[dict[str, Any]]:
        """Events with `seq > after`, then live ones until the run ends. A `ping` is yielded
        when nothing happened for a while so proxies keep the connection open."""
        index = max(after + 1, 0)
        while True:
            async with self._changed:
                if index >= len(self.events) and not self.done:
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self._changed.wait(), KEEPALIVE_EVERY)
                batch = self.events[index:]
                finished = self.done
            if not batch and not finished:
                yield {"type": "ping", "run_id": str(self.run_id)}
                continue
            for event in batch:
                yield event
            index += len(batch)
            if finished and index >= len(self.events):
                return


class RunHub:
    def __init__(self) -> None:
        self._channels: dict[uuid.UUID, RunChannel] = {}

    def get(self, run_id: uuid.UUID) -> RunChannel | None:
        self._evict()
        return self._channels.get(run_id)

    def is_running_here(self, run_id: uuid.UUID) -> bool:
        channel = self._channels.get(run_id)
        return channel is not None and not channel.done

    def launch(
        self,
        run_id: uuid.UUID,
        thread_id: uuid.UUID,
        user_id: uuid.UUID,
        work: Callable[[RunChannel], Awaitable[None]],
    ) -> RunChannel:
        """Start `work(channel)` as its own task. The channel is closed when it ends."""
        self._evict()
        channel = RunChannel(run_id, thread_id, user_id)
        self._channels[run_id] = channel

        async def body() -> None:
            beat = asyncio.create_task(_heartbeat(run_id))
            try:
                await work(channel)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - work handles its own failures; never leak
                log.exception("ai_run_task_crashed", extra={"run_id": str(run_id)})
            finally:
                beat.cancel()
                with contextlib.suppress(Exception):
                    await kv.delete(alive_key(run_id))
                await channel.close()

        channel.task = asyncio.create_task(body(), name=f"ai-run-{run_id}")
        return channel

    async def wait(self, run_id: uuid.UUID, grace: float) -> bool:
        """Wait for a local run's task to finish. True when it is no longer running here."""
        channel = self._channels.get(run_id)
        if channel is None or channel.task is None:
            return True
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(asyncio.shield(channel.task), grace)
        return channel.task.done()

    async def shutdown(self) -> None:
        tasks = [c.task for c in self._channels.values() if c.task and not c.task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._channels.clear()

    def _evict(self) -> None:
        now = time.monotonic()
        for run_id in [
            rid
            for rid, c in self._channels.items()
            if c.finished_at is not None and now - c.finished_at > RETAIN_FINISHED
        ]:
            del self._channels[run_id]


async def is_alive(run_id: uuid.UUID) -> bool:
    """Is some process (this one or another worker) still executing this run?"""
    if hub.is_running_here(run_id):
        return True
    try:
        return bool(await kv.get(alive_key(run_id)))
    except Exception:  # noqa: BLE001
        return False


async def _heartbeat(run_id: uuid.UUID) -> None:
    while True:
        with contextlib.suppress(Exception):
            await kv.set(alive_key(run_id), "1", HEARTBEAT_TTL)
        await asyncio.sleep(HEARTBEAT_EVERY)


hub = RunHub()
