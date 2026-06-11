from app.core.workflow.executor_actions import WorkflowExecutorActionMixin


class DummySendConfirmationExecutor(WorkflowExecutorActionMixin):
    def __init__(self, timeout):
        self._site_advanced_config = {
            "send_confirmation_check_timeout": timeout,
        }

    @staticmethod
    def _coerce_float(value, default, minimum=None):
        try:
            result = float(value)
        except Exception:
            result = float(default)
        if minimum is not None:
            result = max(result, minimum)
        return result


def test_send_confirmation_timeout_scales_with_prompt_length():
    executor = DummySendConfirmationExecutor(1.5)

    assert executor._get_adaptive_send_confirmation_check_timeout(0) == 1.5
    assert executor._get_adaptive_send_confirmation_check_timeout(50000) == 2.5
    assert executor._get_adaptive_send_confirmation_check_timeout(100000) == 3.5


def test_send_confirmation_timeout_is_capped_at_ten_seconds():
    executor = DummySendConfirmationExecutor(6.0)

    assert executor._get_adaptive_send_confirmation_check_timeout(500000) == 10.0
