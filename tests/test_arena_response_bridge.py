import json
import threading

from app.services import result_event_bridge
from app.services.command_engine_results import CommandEngineResultsMixin
from app.services.request_manager import request_manager


def _arena_line(prefix, payload):
    return f"{prefix}:{json.dumps(payload, ensure_ascii=False)}"


def test_arena_result_bridge_extracts_both_battle_sides():
    raw_body = "\n".join(
        [
            _arena_line("a0", "left one"),
            _arena_line("b0", "right one"),
            _arena_line("a0", " left two"),
            _arena_line("b0", " right two"),
            _arena_line("ad", {"finishReason": "stop"}),
            _arena_line("bd", {"finishReason": "stop"}),
        ]
    )

    event = result_event_bridge._build_event(
        {
            "event": {"url": "https://arena.ai/nextjs-api/stream/create-evaluation", "status": 200},
            "raw_body": raw_body,
            "parse_result": {"done": True, "selected_side": "left"},
            "parser_id": "lmarena_battle_side_left",
            "session_id": "arena_1",
        },
        {},
    )

    assert event is not None
    assert event["response_a"] == "left one left two"
    assert event["response_b"] == "right one right two"

    payload = result_event_bridge._arena_command_result_payload(event)
    assert payload["default_response"] == "left one left two"
    assert payload["response_b"] == "right one right two"


class _Matcher(CommandEngineResultsMixin):
    def __init__(self):
        self._lock = threading.Lock()

    @staticmethod
    def _normalize_match_rule(rule):
        value = str(rule or "").strip().lower()
        if value in {"contains", "include", "includes"}:
            return "contains"
        if value in {"not_equals", "not_equal", "ne"}:
            return "not_equals"
        return "equals"


def test_command_result_event_match_can_filter_arena_response_content():
    matcher = _Matcher()
    event = {
        "source_command_id": "evt_arena_response",
        "source_command_name": "ARENA_RESPONSE",
        "summary": "Arena 响应已捕获: A=4 字, B=5 字",
        "result": "",
        "informative": True,
        "response_a": "left answer",
        "response_b": "right answer",
        "default_response": "left answer",
    }

    assert matcher._result_event_matches_trigger(
        {
            "command_ids": ["evt_arena_response"],
            "informative_only": True,
            "expected_value": "right answer",
            "match_rule": "contains",
        },
        event,
    )

    assert not matcher._result_event_matches_trigger(
        {
            "command_ids": ["evt_arena_response"],
            "informative_only": True,
            "expected_value": "missing text",
            "match_rule": "contains",
        },
        event,
    )


def test_external_response_preserves_claude_hit_marker():
    ctx = request_manager.create_request()
    request_manager.start_request(ctx, tab_id="arena_test")
    try:
        request_manager.update_request_metadata(
            ctx.request_id,
            response_text="CLAUDE-HIT source=test preview=claude",
            has_response_text=True,
        )

        assert request_manager.capture_external_response(
            ctx.request_id,
            "actual arena response",
        )

        with ctx._lock:
            stored = str(ctx.monitor.get("response_text") or "")
        assert "CLAUDE-HIT" in stored
        assert "actual arena response" in stored
    finally:
        if not ctx.is_terminal():
            request_manager.finish_request(ctx, success=True)
