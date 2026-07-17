from app.core.workflow.executor_actions import WorkflowExecutorActionMixin


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
