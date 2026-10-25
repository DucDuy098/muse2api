"""Pub/sub for live task-progress SSE. The 7 status-mutation points in app.py
run inside worker threads (not the asyncio loop), so publish() must hop onto
the loop via call_soon_threadsafe — plain asyncio.Queue is not safe to touch
from another thread otherwise.
"""
from __future__ import annotations

import asyncio


class TaskBus:
    def __init__(self):
        self._subs: dict[str, list[asyncio.Queue]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Call once from the main asyncio loop (e.g. app startup)."""
        self._loop = loop

    async def subscribe(self, task_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subs.setdefault(task_id, []).append(q)
        return q

    def unsubscribe(self, task_id: str, q: asyncio.Queue) -> None:
        subs = self._subs.get(task_id)
        if subs and q in subs:
            subs.remove(q)
            if not subs:
                self._subs.pop(task_id, None)

    def publish(self, task_id: str, event: dict) -> None:
        """Call this from the asyncio loop thread."""
        for q in self._subs.get(task_id, []):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def publish_threadsafe(self, task_id: str, event: dict) -> None:
        """Call this from a worker thread (the 7 mutation points in app.py)."""
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self.publish, task_id, event)


TASK_BUS = TaskBus()


def _demo() -> None:
    """ponytail smoke test: the one tricky bit here is the thread->loop
    handoff — verify a worker thread's publish actually reaches a subscriber
    awaiting on the main loop, instead of silently dropping the event."""
    import threading

    async def main():
        loop = asyncio.get_running_loop()
        TASK_BUS.bind_loop(loop)
        q = await TASK_BUS.subscribe("t1")

        def worker():
            TASK_BUS.publish_threadsafe("t1", {"status": "completed"})

        threading.Thread(target=worker).start()
        event = await asyncio.wait_for(q.get(), timeout=2.0)
        assert event == {"status": "completed"}, event
        TASK_BUS.unsubscribe("t1", q)
        print("task_events smoke test: OK")

    asyncio.run(main())


if __name__ == "__main__":
    _demo()
