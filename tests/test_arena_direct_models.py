import contextlib
import json
from pathlib import Path

import pytest

from app.api import chat as chat_api
from app.core.workflow.executor_actions import WorkflowExecutorActionMixin
from app.services.arena_direct_models import (
    ARENA_DIRECT_MODEL_PREFIX,
    build_arena_direct_model_id,
    build_openai_model_entries,
    is_arena_direct_model_id,
    parse_arena_direct_model_id,
    read_arena_direct_models_from_tab,
)
from app.utils.model_routing import inspect_model_route


MODEL_UUID = "019c6d29-a30c-7e20-9bd0-6650af926623"
MODEL_TRIGGER_SELECTOR = 'button[aria-haspopup="dialog"]:has(span.flex-1.truncate.text-left)'


class _CatalogTab:
    def run_js(self, script, timeout=None):
        assert '"initialModels":' in script
        assert timeout == 3.0
        return [
            {
                "arena_model_id": MODEL_UUID,
                "name": "claude-sonnet-4-6-vertex",
                "public_name": "claude-sonnet-4-6",
                "display_name": "claude-sonnet-4-6",
                "provider": "googleVertexAnthropic",
                "organization": "anthropic",
            },
            {
                "arena_model_id": MODEL_UUID,
                "name": "duplicate-id",
                "public_name": "duplicate",
            },
            {
                "arena_model_id": "second-id",
                "name": "claude-sonnet-4-6-vertex",
                "public_name": "duplicate-name",
            },
            {"arena_model_id": "", "name": "invalid"},
        ]


def test_arena_direct_model_ids_are_stable_and_route_through_arena():
    model_id = build_arena_direct_model_id(MODEL_UUID)

    assert model_id == f"{ARENA_DIRECT_MODEL_PREFIX}{MODEL_UUID}"
    assert parse_arena_direct_model_id(model_id.upper()) == MODEL_UUID.upper()
    assert is_arena_direct_model_id(model_id)

    route = inspect_model_route(
        model_id,
        [
            {
                "current_domain": "arena.ai",
                "route_domain": "arena.ai",
                "exposed_model_name": "arena.ai",
            }
        ],
    )
    assert route["route_domain"] == "arena.ai"
    assert route["match_type"] == "prefix"


def test_catalog_normalization_deduplicates_and_builds_openai_entries():
    models = read_arena_direct_models_from_tab(_CatalogTab())

    assert models == [
        {
            "arena_model_id": MODEL_UUID,
            "name": "claude-sonnet-4-6-vertex",
            "public_name": "claude-sonnet-4-6",
            "display_name": "claude-sonnet-4-6",
            "provider": "googleVertexAnthropic",
            "organization": "anthropic",
        }
    ]

    entries = build_openai_model_entries(models, created=123)
    assert entries == [
        {
            "id": f"{ARENA_DIRECT_MODEL_PREFIX}{MODEL_UUID}",
            "object": "model",
            "type": "model",
            "created": 123,
            "owned_by": "anthropic",
            "display_name": "Arena Direct · claude-sonnet-4-6",
        }
    ]


def test_global_model_list_merges_arena_direct_models(monkeypatch):
    class _TabPool:
        @staticmethod
        def get_tabs_with_index():
            return []

    class _Browser:
        tab_pool = _TabPool()

    monkeypatch.setattr(chat_api, "get_browser", lambda auto_connect=False: _Browser())
    monkeypatch.setattr(
        chat_api,
        "list_arena_direct_models",
        lambda _browser: [
            {
                "arena_model_id": MODEL_UUID,
                "name": "claude-sonnet-4-6-vertex",
                "public_name": "claude-sonnet-4-6",
                "display_name": "claude-sonnet-4-6",
                "organization": "anthropic",
            }
        ],
    )

    entries = chat_api._collect_model_entries()

    assert any(item["id"] == build_arena_direct_model_id(MODEL_UUID) for item in entries)


class _Element:
    def __init__(self, text="", data_value=""):
        self.text = text
        self._data_value = data_value

    def attr(self, name):
        return self._data_value if name == "data-value" else ""


class _TextHandler:
    def __init__(self):
        self.calls = []

    def fill_via_clipboard_no_click(self, element, text):
        self.calls.append((element, text))


class _ActionHarness(WorkflowExecutorActionMixin):
    def __init__(self, current_label):
        self.trigger = _Element(text=current_label)
        self.search = _Element()
        self.option = _Element(data_value="claude-sonnet-4-6-vertex")
        self._text_handler = _TextHandler()
        self.clicks = []
        self.tab = object()

    @contextlib.contextmanager
    def _page_interaction_slot(self, *_args, **_kwargs):
        yield True

    def _check_cancelled(self):
        return False

    @staticmethod
    def _coerce_float(value, default, minimum=0.0):
        return max(minimum, float(value if value is not None else default))

    @staticmethod
    def _compact_log_value(value, _max_len=100):
        return str(value)

    def _find_visible_elements(self, selector):
        if selector == MODEL_TRIGGER_SELECTOR:
            return [self.trigger]
        if selector == 'input[placeholder="Search models"]':
            return [self.search]
        if selector == '[role="option"][data-value]':
            return [self.option]
        return []

    def _stealth_click_element(self, element, **_kwargs):
        self.clicks.append(element)
        if element is self.option:
            self.trigger.text = "claude-sonnet-4-6"

    def _close_arena_model_dialog(self):
        raise AssertionError("successful selection should not need dialog cleanup")


class _BattleActionHarness(_ActionHarness):
    def __init__(self):
        super().__init__(current_label="Max")
        self.mode_button = _Element(text="Battle Mode")
        self.direct_option = _Element(text="Direct Chat with 1 model at a time")
        self.direct_mode = False

    def _find_visible_elements(self, selector):
        if selector == MODEL_TRIGGER_SELECTOR:
            return [self.trigger] if self.direct_mode else []
        if selector == 'button[role="combobox"]':
            return [self.mode_button]
        if selector == '[role="option"]':
            return [self.direct_option]
        return super()._find_visible_elements(selector)

    def _stealth_click_element(self, element, **kwargs):
        self.clicks.append(element)
        if element is self.direct_option:
            self.direct_mode = True
            self.mode_button.text = "Direct"
        elif element is self.option:
            self.trigger.text = "claude-sonnet-4-6"


@pytest.fixture
def resolved_model(monkeypatch):
    model = {
        "arena_model_id": MODEL_UUID,
        "name": "claude-sonnet-4-6-vertex",
        "public_name": "claude-sonnet-4-6",
        "display_name": "claude-sonnet-4-6",
    }
    monkeypatch.setattr(
        "app.core.workflow.executor_actions.resolve_arena_direct_model",
        lambda _tab, _requested: model,
    )
    return model


def test_select_model_is_zero_interaction_when_already_selected(resolved_model):
    harness = _ActionHarness(current_label="claude-sonnet-4-6")

    harness._execute_select_model(
        selector=MODEL_TRIGGER_SELECTOR,
        target_key="model_select_btn",
        value={"timeout": 1},
        context={"model": build_arena_direct_model_id(MODEL_UUID)},
        optional=False,
    )

    assert harness.clicks == []
    assert harness._text_handler.calls == []


def test_select_model_uses_one_menu_click_and_one_exact_option_click(resolved_model):
    harness = _ActionHarness(current_label="Max")

    harness._execute_select_model(
        selector=MODEL_TRIGGER_SELECTOR,
        target_key="model_select_btn",
        value={"timeout": 1},
        context={"model": build_arena_direct_model_id(MODEL_UUID)},
        optional=False,
    )

    assert harness.clicks == [harness.trigger, harness.option]
    assert harness._text_handler.calls == [
        (harness.search, "claude-sonnet-4-6-vertex")
    ]


def test_select_model_switches_battle_to_direct_before_selecting(resolved_model):
    harness = _BattleActionHarness()

    harness._execute_select_model(
        selector=MODEL_TRIGGER_SELECTOR,
        target_key="model_select_btn",
        value={"timeout": 1},
        context={"model": build_arena_direct_model_id(MODEL_UUID)},
        optional=False,
    )

    assert harness.clicks == [
        harness.mode_button,
        harness.direct_option,
        harness.trigger,
        harness.option,
    ]


def test_arena_main_direct_workflow_selects_model_before_filling_prompt():
    sites_path = Path(__file__).parents[1] / "config" / "sites.json"
    sites = json.loads(sites_path.read_text(encoding="utf-8"))
    preset = sites["arena.ai"]["presets"]["主预设-直连模式"]
    actions = [step["action"] for step in preset["workflow"]]

    assert preset["selectors"]["model_select_btn"] == MODEL_TRIGGER_SELECTOR
    assert 'href="/code"' in preset["selectors"]["new_chat_btn"]
    assert actions.index("SELECT_MODEL") < actions.index("FILL_INPUT")
