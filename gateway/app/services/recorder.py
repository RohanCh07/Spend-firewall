"""Writes usage events and alerts to Postgres off the hot path.

The request handler only does `queue.put_nowait`; a background task batches
inserts. If the queue is full we drop the event and count it, rather than slow
down agents (Redis counters, which enforce budgets, are already updated).
"""

import asyncio
import logging
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.storage.db import AlertLog, UsageEvent

log = logging.getLogger("spendfirewall.recorder")


class Recorder:
    def __init__(self, sessionmaker: async_sessionmaker, max_queue: int = 50_000, batch: int = 200):
        self.sessionmaker = sessionmaker
        self.queue: asyncio.Queue[Any] = asyncio.Queue(max_queue)
        self.batch = batch
        self.dropped = 0
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        try:
            await asyncio.wait_for(self.flush(), 10)
        finally:
            if self._task:
                self._task.cancel()

    def usage(self, **fields: Any) -> None:
        self._put(UsageEvent(**fields))

    def alert(self, **fields: Any) -> None:
        self._put(AlertLog(**fields))

    def _put(self, row: Any) -> None:
        try:
            self.queue.put_nowait(row)
        except asyncio.QueueFull:
            self.dropped += 1

    async def flush(self) -> None:
        """Wait until every queued row is written."""
        if self._task and not self._task.done():
            await self.queue.join()
            return
        rows = []
        while not self.queue.empty():
            rows.append(self.queue.get_nowait())
            self.queue.task_done()
        await self._write(rows)

    async def _write(self, rows: list[Any]) -> None:
        if not rows:
            return
        try:
            async with self.sessionmaker() as s:
                s.add_all(rows)
                await s.commit()
        except Exception:  # noqa: BLE001 - never crash the writer
            log.exception("failed to write %d usage rows", len(rows))

    async def _run(self) -> None:
        while True:
            rows = [await self.queue.get()]
            await asyncio.sleep(0.05)  # let a batch accumulate
            while len(rows) < self.batch and not self.queue.empty():
                rows.append(self.queue.get_nowait())
            try:
                await self._write(rows)
            finally:
                for _ in rows:
                    self.queue.task_done()
