from pathlib import Path

from app.api.config_route_models import (
    SiteAdvancedConfigRequest,
    _extract_site_advanced_update_payload,
)
from app.models.schemas import PRESET_ADVANCED_FIELDS, get_default_site_advanced_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / "app" / "core" / "browser" / "workflow.py"
CONFIG_TAB = PROJECT_ROOT / "static" / "js" / "components" / "ConfigTab.js"


def test_skip_new_chat_on_retry_is_preset_advanced_field():
    assert "skip_new_chat_on_retry" in PRESET_ADVANCED_FIELDS
    assert get_default_site_advanced_config()["skip_new_chat_on_retry"] is False


def test_skip_new_chat_on_retry_flat_payload_is_preserved_for_preset_scope():
    body = SiteAdvancedConfigRequest(
        preset_name="主预设",
        skip_new_chat_on_retry=True,
    )

    payload = _extract_site_advanced_update_payload(body, preset_scope=True)

    assert payload == {"skip_new_chat_on_retry": True}


def test_skip_new_chat_on_retry_nested_payload_is_preserved_for_preset_scope():
    body = SiteAdvancedConfigRequest(
        preset_name="主预设",
        advanced={"skip_new_chat_on_retry": True},
    )

    payload = _extract_site_advanced_update_payload(body, preset_scope=True)

    assert payload == {"skip_new_chat_on_retry": True}


def test_workflow_attempt_controls_retry_skip_new_chat_gate():
    source = WORKFLOW.read_text(encoding="utf-8")

    assert 'setattr(session, "_workflow_attempt", attempt)' in source
    assert 'setattr(session, "_workflow_attempt", 0)' in source
    assert 'advanced_config.get("skip_new_chat_on_retry", False)' in source
    assert "retry_skip_new_chat" in source


def test_config_tab_exposes_skip_new_chat_on_retry_control():
    source = CONFIG_TAB.read_text(encoding="utf-8")

    assert "skip_new_chat_on_retry" in source
    assert "updateSkipNewChatOnRetry" in source
    assert "重试轮跳过新建对话" in source
