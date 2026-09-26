"""Redis/ARQ ChatOps queue, separate from document ingestion."""
from __future__ import annotations
import asyncio
import os
class QueueUnavailable(RuntimeError): pass
class ChatOpsQueue:
    def __init__(self, *, redis_url=None, queue_name=None, ttl=600):
        self.redis_url=redis_url or os.environ.get("REDIS_URL","redis://redis:6379/0"); self.queue_name=queue_name or os.environ.get("CHATOPS_QUEUE","chatops"); self.ttl=ttl
    async def enqueue(self, job):
        try:
            from arq.connections import RedisSettings, create_pool
        except ImportError as exc: raise QueueUnavailable("ARQ is not installed") from exc
        redis = None
        key = f"chatops:event:{job['team_id']}:{job['event_id']}"
        claimed = False
        try:
            redis = await asyncio.wait_for(create_pool(RedisSettings.from_dsn(self.redis_url)), 2)
            claimed = await asyncio.wait_for(redis.set(key,"1",ex=self.ttl,nx=True), 2)
            if not claimed:
                return False
            await asyncio.wait_for(
                redis.enqueue_job("process_chatops_event",job,_queue_name=self.queue_name,_job_id=f"chatops:{job['team_id']}:{job['event_id']}"),
                2,
            )
            return True
        except BaseException as exc:
            if claimed and redis is not None:
                try:
                    await asyncio.wait_for(redis.delete(key), 1)
                except BaseException:
                    pass
            if isinstance(exc, QueueUnavailable):
                raise
            raise QueueUnavailable("enqueue failed") from exc
        finally:
            if redis is not None:
                try:
                    await asyncio.wait_for(redis.aclose(), 1)
                except BaseException:
                    pass
