"""Durable hosted execution; queue messages contain only a run ID, never API keys."""

import asyncio
import uuid

from vercel.queue import Message, send, subscribe

from . import config, storage
from .engine import execute_run
from .schemas import RunRequest

TOPIC = "parallax-research"


async def enqueue(run_id):
    await send(TOPIC, {"run_id": run_id}, idempotency_key=run_id, retention=3600)


async def process_run(run_id):
    saved = await asyncio.to_thread(storage.get_run, run_id)
    if not saved or saved["status"] != "running":
        return
    token = uuid.uuid4().hex
    if not await asyncio.to_thread(storage.claim, run_id, token):
        # A duplicate delivery must retry later rather than execute the paid work concurrently.
        raise storage.LeaseLostError("This round is already being processed.")
    request = RunRequest(**saved["request"])
    histories = (
        {model: await asyncio.to_thread(storage.research_history, saved["session_id"], model, run_id) for model in request.models}
        if not request.fresh
        else {}
    )
    task = None
    heartbeat = None

    async def watch():
        while True:
            await asyncio.sleep(5)
            if not await asyncio.to_thread(storage.renew, run_id, token):
                return

    try:
        task = asyncio.create_task(execute_run(request, run_id, config.keys(), histories, token=token))
        heartbeat = asyncio.create_task(watch())
        # The longest existing research + comparison budget is 600s. Leave platform headroom.
        async with asyncio.timeout(690):
            done, _ = await asyncio.wait((task, heartbeat), return_when=asyncio.FIRST_COMPLETED)
            if heartbeat in done:
                heartbeat.result()
                if storage.get_run(run_id)["status"] == "running":
                    raise storage.LeaseLostError("Research ownership changed.")
                return
            await task
    except TimeoutError:
        storage.finish(
            run_id,
            "failed",
            {"reports": list(storage.completed_reports(run_id).values())},
            token=token,
            terminal={"type": "error", "message": "The research time limit was reached. Completed answers have been saved."},
        )
    finally:
        for pending in (task, heartbeat):
            if pending:
                pending.cancel()
        await asyncio.gather(*(t for t in (task, heartbeat) if t), return_exceptions=True)
        await asyncio.to_thread(storage.release, run_id, token)


@subscribe(topic=TOPIC, max_concurrency=2, max_attempts=3, retry_after=65)
async def research_job(message: Message[dict[str, str]]) -> None:
    storage.init()
    run_id = message.payload["run_id"]
    try:
        await process_run(run_id)
    except Exception:
        if message.metadata.delivery_count >= 3:
            # Do not expose database/provider exceptions or credentials to the UI or logs.
            storage.finish(
                run_id,
                "failed",
                {"reports": list(storage.completed_reports(run_id).values())},
                terminal={
                    "type": "error",
                    "message": "The research worker could not finish after three attempts. Completed answers have been saved.",
                },
                unleased=True,
            )
            return
        raise RuntimeError("Research worker temporarily unavailable; queued for retry.") from None
