import asyncio
import threading
import time

from app.services import request_lifecycle
from app.services.request_lifecycle import cleanup_worker_thread_after_request
from app.services.request_manager import RequestContext, RequestStatus


def test_completed_worker_cleanup_defers_retirement(monkeypatch):
    retire_calls = []
    scheduled_calls = []
    release_event = threading.Event()

    def slow_cleanup_worker():
        release_event.wait(timeout=2.0)

    worker = threading.Thread(target=slow_cleanup_worker, daemon=True)
    worker.start()

    ctx = RequestContext(request_id="req-test-completed")
    ctx.mark_running("arena_1")
    ctx.mark_completed()

    monkeypatch.setattr(
        request_lifecycle,
        "retire_bound_tab_after_worker_leak",
        lambda *_args, **_kwargs: retire_calls.append((_args, _kwargs)),
    )

    def fake_schedule(worker_thread, request_ctx, reason, *, delay_sec):
        scheduled_calls.append((worker_thread, request_ctx, reason, delay_sec))

    monkeypatch.setattr(
        request_lifecycle,
        "schedule_completed_worker_retire_check",
        fake_schedule,
    )

    still_alive = asyncio.run(
        cleanup_worker_thread_after_request(
            worker,
            ctx,
            completed=True,
            completed_join_timeout=0.01,
            completed_retire_delay=30.0,
        )
    )

    release_event.set()
    worker.join(timeout=1.0)

    assert still_alive is True
    assert ctx.status == RequestStatus.COMPLETED
    assert ctx.cancel_reason is None
    assert retire_calls == []
    assert len(scheduled_calls) == 1
    assert scheduled_calls[0][1] is ctx
    assert scheduled_calls[0][2] == "worker_cleanup_timeout"


def test_unfinished_worker_cleanup_still_retires(monkeypatch):
    retire_calls = []
    release_event = threading.Event()

    def stuck_worker():
        release_event.wait(timeout=2.0)

    worker = threading.Thread(target=stuck_worker, daemon=True)
    worker.start()

    ctx = RequestContext(request_id="req-test-running")
    ctx.mark_running("arena_1")

    monkeypatch.setattr(
        request_lifecycle,
        "retire_bound_tab_after_worker_leak",
        lambda *_args, **_kwargs: retire_calls.append((_args, _kwargs)),
    )

    still_alive = asyncio.run(
        cleanup_worker_thread_after_request(
            worker,
            ctx,
            completed=False,
            join_timeout=0.01,
        )
    )

    release_event.set()
    worker.join(timeout=1.0)

    assert still_alive is True
    assert ctx.status == RequestStatus.CANCELLED
    assert ctx.cancel_reason == "cleanup"
    assert len(retire_calls) == 1
    assert retire_calls[0][0][0] is ctx
    assert retire_calls[0][0][1] == "worker_cleanup_timeout"


def test_completed_worker_cleanup_finishes_without_background_schedule(monkeypatch):
    scheduled_calls = []

    def quick_worker():
        time.sleep(0.01)

    worker = threading.Thread(target=quick_worker, daemon=True)
    worker.start()

    ctx = RequestContext(request_id="req-test-quick")
    ctx.mark_running("arena_1")
    ctx.mark_completed()

    monkeypatch.setattr(
        request_lifecycle,
        "schedule_completed_worker_retire_check",
        lambda *_args, **_kwargs: scheduled_calls.append((_args, _kwargs)),
    )

    still_alive = asyncio.run(
        cleanup_worker_thread_after_request(
            worker,
            ctx,
            completed=True,
            completed_join_timeout=1.0,
        )
    )

    assert still_alive is False
    assert ctx.status == RequestStatus.COMPLETED
    assert scheduled_calls == []
