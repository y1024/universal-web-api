import asyncio
import threading
import time

from starlette.responses import StreamingResponse

from app.api.anthropic_routes import _anthropic_stream_from_openai
from app.services.request_manager import RequestContext
from app.services import result_event_bridge


class _TrackingAsyncIterator:
    def __init__(self):
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.sleep(60)
        raise StopAsyncIteration

    async def aclose(self):
        self.closed = True


def test_response_chunk_refreshes_idle_activity_without_hard_timeout(monkeypatch):
    ctx = RequestContext(request_id="req-test")
    ctx.mark_running()
    original_timeout_start = ctx.started_at_monotonic
    ctx.last_activity_at = 1.0

    from app.services.request_manager import request_manager

    request_manager.capture_response_chunk(ctx, ": keepalive\n\n")

    assert ctx.last_activity_at > 1.0
    assert ctx.started_at_monotonic == original_timeout_start


def test_result_event_dedupe_is_atomic_and_bounded(monkeypatch):
    appended = []
    append_lock = threading.Lock()

    def fake_append(event):
        time.sleep(0.01)
        with append_lock:
            appended.append(event)

    monkeypatch.setattr(result_event_bridge, "_append_event", fake_append)
    monkeypatch.setattr(result_event_bridge, "_get_dedupe_max_entries", lambda: 2)
    with result_event_bridge._DEDUPE_LOCK:
        result_event_bridge._LAST_DIGEST_BY_KEY.clear()

    event = {
        "event_id": "same-digest",
        "session_id": "session",
        "completion_id": "completion",
        "conversation_id": "conversation",
        "parser_id": "parser",
    }
    results = []

    def emit():
        results.append(result_event_bridge._dedupe_and_append(dict(event)))

    try:
        threads = [threading.Thread(target=emit) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(appended) == 1
        assert results.count(True) == 1

        for index in range(3):
            distinct = dict(event, event_id=f"digest-{index}", completion_id=str(index))
            assert result_event_bridge._dedupe_and_append(distinct)

        assert len(result_event_bridge._LAST_DIGEST_BY_KEY) == 2
    finally:
        with result_event_bridge._DEDUPE_LOCK:
            result_event_bridge._LAST_DIGEST_BY_KEY.clear()


def test_anthropic_stream_closes_upstream_after_initial_event():
    async def exercise():
        upstream = _TrackingAsyncIterator()
        response = StreamingResponse(upstream, media_type="text/event-stream")
        translated = _anthropic_stream_from_openai(response, "test-model")

        first_event = await anext(translated)
        assert "event: message_start" in first_event
        assert upstream.closed is False

        await translated.aclose()
        assert upstream.closed is True

    asyncio.run(exercise())
