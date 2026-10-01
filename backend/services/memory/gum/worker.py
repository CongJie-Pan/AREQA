"""Debounced observation queue; the runtime supplies its processing callback."""

import asyncio
import logging

logger = logging.getLogger(__name__)

class ObservationQueueWorker:
    def __init__(self, process_callback, debounce_seconds: float = 3.0):
        self.queue = asyncio.Queue()
        self.process_callback = process_callback
        self.debounce_seconds = debounce_seconds
        self._task = None

    async def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._worker())

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def push(
        self,
        user_id: str,
        observation: str,
        *,
        sync_to_working_memory: bool = True,
        conversation_id: str = "",
    ):
        await self.queue.put({
            "user_id": user_id,
            "observation": observation,
            "sync_to_working_memory": sync_to_working_memory,
            "conversation_id": conversation_id,
        })

    async def _worker(self):
        from collections import defaultdict
        while True:
            try:
                # Wait for at least one item
                first = await self.queue.get()

                # We will process per-user. Let's collect items per user.
                items_by_route = defaultdict(list)
                first_key = (
                    first["user_id"],
                    first["sync_to_working_memory"],
                    first["conversation_id"],
                )
                items_by_route[first_key].append(first["observation"])

                # Debounce window
                await asyncio.sleep(self.debounce_seconds)

                # Collect any other items that arrived during the window
                while not self.queue.empty():
                    try:
                        item = self.queue.get_nowait()
                        route_key = (
                            item["user_id"],
                            item["sync_to_working_memory"],
                            item["conversation_id"],
                        )
                        items_by_route[route_key].append(item["observation"])
                    except asyncio.QueueEmpty:
                        break

                # Process the batch
                for (uid, sync_to_working, conversation_id), items in items_by_route.items():
                    if items:
                        await self.process_callback(
                            uid,
                            items,
                            sync_to_working_memory=sync_to_working,
                            conversation_id=conversation_id,
                        )

                # Mark as done
                total_items = sum(len(v) for v in items_by_route.values())
                for _ in range(total_items):
                    self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("gum.worker_failed reason=%s", type(e).__name__)
                await asyncio.sleep(1)
