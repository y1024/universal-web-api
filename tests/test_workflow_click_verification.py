from app.core.workflow.executor_actions import WorkflowExecutorActionMixin
from app.core.page_lifecycle import BACKGROUND_WAKE_CDP_TIMEOUT


class _StrictRunJsTab:
    def __init__(self):
        self.payload = None

    def run_js(self, script, argument, timeout):
        assert isinstance(argument, dict)
        assert "payload.probes" in script
        assert timeout == 1.0
        self.payload = argument
        return [
            {
                "target": probe["target"],
                "state": probe["state"],
                "present": False,
                "visible": False,
                "matched": probe["state"] == "absent",
            }
            for probe in argument["probes"]
        ]


def test_click_verification_wraps_probe_list_for_drissionpage():
    executor = WorkflowExecutorActionMixin.__new__(WorkflowExecutorActionMixin)
    executor.tab = _StrictRunJsTab()
    executor._selectors = {"retry button": "button.retry"}

    result = executor._probe_click_verification_conditions(
        [{"target": "retry button", "state": "absent"}]
    )

    assert executor.tab.payload == {
        "probes": [
            {
                "target": "retry button",
                "selector": "button.retry",
                "state": "absent",
            }
        ]
    }
    assert result == [
        {
            "target": "retry button",
            "state": "absent",
            "present": False,
            "visible": False,
            "matched": True,
        }
    ]


class _RectUnavailableElement:
    _backend_id = 4225

    @property
    def rect(self):
        raise RuntimeError("rect unavailable")


class _BoxModelTab:
    def __init__(self):
        self.calls = []

    def run_cdp(self, method, **kwargs):
        self.calls.append((method, kwargs))
        return {
            "model": {
                "content": [10, 20, 110, 20, 110, 60, 10, 60],
            }
        }


def test_element_position_falls_back_to_native_cdp_box_model():
    executor = WorkflowExecutorActionMixin.__new__(WorkflowExecutorActionMixin)
    executor.tab = _BoxModelTab()

    position = executor._get_element_viewport_pos(_RectUnavailableElement())

    assert position == (60, 40)
    assert executor.tab.calls == [
        (
            "DOM.getBoxModel",
            {
                "backendNodeId": 4225,
                "_timeout": BACKGROUND_WAKE_CDP_TIMEOUT,
            },
        )
    ]


def test_box_model_skips_degenerate_content_quad():
    executor = WorkflowExecutorActionMixin.__new__(WorkflowExecutorActionMixin)

    class _BorderBoxModelTab:
        @staticmethod
        def run_cdp(_method, **_kwargs):
            return {
                "model": {
                    "content": [20, 30, 20, 30, 20, 30, 20, 30],
                    "border": [15, 25, 125, 25, 125, 65, 15, 65],
                }
            }

    executor.tab = _BorderBoxModelTab()

    assert executor._get_element_viewport_pos(_RectUnavailableElement()) == (70, 45)
