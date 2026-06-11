from app.core.workflow.executor_actions import WorkflowExecutorActionMixin
from app.core.workflow.text_input import TextInputHandler
from app.utils import human_mouse


def test_key_combo_lognormal_delay_stays_within_bounds():
    values = [
        TextInputHandler._bounded_lognormal_delay(0.01, 0.04)
        for _ in range(100)
    ]

    assert all(0.01 <= value <= 0.04 for value in values)
    assert TextInputHandler._bounded_lognormal_delay(0.03, 0.01) == 0.03


def test_smooth_move_mouse_glides_short_non_tiny_moves(monkeypatch):
    events = []

    def fake_dispatch(_tab, x, y, buttons=0):
        events.append((x, y, buttons))
        return True

    monkeypatch.setattr(human_mouse, "_dispatch_mouse_move", fake_dispatch)
    monkeypatch.setattr(human_mouse.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(human_mouse.random, "randint", lambda start, _end: start)

    assert human_mouse.smooth_move_mouse(object(), (0, 0), (4, 0)) == (4, 0)
    assert events == [(4, 0, 0)]

    events.clear()
    assert human_mouse.smooth_move_mouse(object(), (0, 0), (10, 0)) == (10, 0)
    assert len(events) >= 2
    assert events[-1] == (10, 0, 0)


class _DummyExecutor(WorkflowExecutorActionMixin):
    stealth_mode = True

    def _check_cancelled(self):
        return False

    def _smart_delay(self, *_args, **_kwargs):
        return None

    @staticmethod
    def _compact_log_value(value, _limit):
        return str(value)


class _DummyElement:
    def __init__(self):
        self.script = ""

    def run_js(self, script):
        self.script = script
        return {"ok": True, "active": True, "x": 42, "y": 24}


def test_stealth_dom_click_uses_coordinate_event_chain():
    element = _DummyElement()
    executor = _DummyExecutor()

    assert executor._stealth_dom_click_element(element, target_key="send_btn")
    assert "getBoundingClientRect" in element.script
    assert "clientX" in element.script
    assert "pointerdown" in element.script
    assert "mousedown" in element.script
    assert "el.click(" not in element.script
