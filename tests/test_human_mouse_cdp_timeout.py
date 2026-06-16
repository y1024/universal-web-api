import time

import app.utils.human_mouse as human_mouse


class FakeActions:
    def scroll(self, *_args, **_kwargs):
        raise AssertionError("CDP wheel dispatch should not fall back during this test")


class FakeTab:
    def __init__(self):
        self.calls = []
        self.actions = FakeActions()

    def run_cdp(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return {}


def _dispatch_calls(tab):
    return [
        kwargs
        for command, kwargs in tab.calls
        if command == "Input.dispatchMouseEvent"
    ]


def test_mouse_move_dispatch_is_fire_and_forget():
    tab = FakeTab()

    assert human_mouse._dispatch_mouse_move(tab, 12, 34, buttons=1) is True

    assert _dispatch_calls(tab)[0]["_timeout"] == 0


def test_scroll_dispatch_is_fire_and_forget(monkeypatch):
    tab = FakeTab()
    monkeypatch.setattr(human_mouse.random, "randint", lambda _start, _end: 100)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    human_mouse.human_scroll(tab, 100, mouse_x=20, mouse_y=30)

    calls = _dispatch_calls(tab)
    assert len(calls) == 1
    assert calls[0]["type"] == "mouseWheel"
    assert calls[0]["_timeout"] == 0


def test_scroll_path_dispatch_is_fire_and_forget(monkeypatch):
    tab = FakeTab()
    monkeypatch.setattr(human_mouse.random, "randint", lambda _start, _end: 1)
    monkeypatch.setattr(human_mouse.random, "uniform", lambda start, _end: start)
    monkeypatch.setattr(human_mouse.random, "gauss", lambda _mu, _sigma: 0)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    human_mouse.human_scroll_path(tab, (0, 0), (100, 120))

    calls = _dispatch_calls(tab)
    assert any(call["type"] == "mouseWheel" for call in calls)
    assert all(call["_timeout"] == 0 for call in calls)


def test_precise_click_dispatch_is_fire_and_forget(monkeypatch):
    tab = FakeTab()
    monkeypatch.setattr(human_mouse.random, "uniform", lambda start, _end: start)
    monkeypatch.setattr(human_mouse.random, "randint", lambda start, _end: start)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    assert human_mouse.cdp_precise_click(tab, 40, 50, hold_duration=0.04) is True

    calls = _dispatch_calls(tab)
    assert any(call["type"] == "mousePressed" for call in calls)
    assert any(call["type"] == "mouseReleased" for call in calls)
    assert all(call["_timeout"] == 0 for call in calls)


def test_cancel_release_dispatch_is_fire_and_forget():
    tab = FakeTab()

    human_mouse._release_mouse(tab, 9, 10)

    calls = _dispatch_calls(tab)
    assert calls[0]["type"] == "mouseReleased"
    assert calls[0]["_timeout"] == 0
