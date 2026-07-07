from app.api import chat, tab_routes
from app.core.tab_pool_parts.manager import TabPoolManager
from app.utils.model_routing import collect_route_domain_models, inspect_model_route


def _model_ids(tabs):
    return {item["id"] for item in collect_route_domain_models(tabs)}


def test_custom_exposed_model_names_replace_default_route_model_for_custom_tabs():
    tabs = [
        {
            "id": "arena_1",
            "persistent_index": 1,
            "current_domain": "arena.ai",
            "route_domain": "arena.ai",
            "exposed_model_name": "arena-left",
            "model_name_override_source": "tab",
        },
        {
            "id": "arena_2",
            "persistent_index": 2,
            "current_domain": "arena.ai",
            "route_domain": "arena.ai",
            "exposed_model_name": "arena-right",
            "model_name_override_source": "url",
        },
    ]

    ids = _model_ids(tabs)

    assert "arena-left" in ids
    assert "arena-right" in ids
    assert "arena.ai" not in ids

    route = inspect_model_route("arena-left", tabs)
    assert route["route_type"] == "model_name"
    assert route["model_name"] == "arena-left"


def test_default_route_model_only_represents_tabs_without_custom_model_name():
    tabs = [
        {
            "id": "arena_1",
            "persistent_index": 1,
            "current_domain": "arena.ai",
            "route_domain": "arena.ai",
            "exposed_model_name": "arena.ai",
            "model_name_override_source": "",
        },
        {
            "id": "arena_2",
            "persistent_index": 2,
            "current_domain": "arena.ai",
            "route_domain": "arena.ai",
            "exposed_model_name": "arena-special",
            "model_name_override_source": "tab",
        },
    ]

    route = inspect_model_route("arena.ai", tabs)

    assert route["route_type"] == "model_name"
    assert route["model_name"] == "arena.ai"
    assert "arena-special" in _model_ids(tabs)


def test_model_name_target_tab_resolution_round_robins_within_same_name_only():
    class FakePool:
        def __init__(self):
            self.tabs = [
                {"persistent_index": 1, "status": "idle", "exposed_model_name": "arena-left"},
                {"persistent_index": 2, "status": "idle", "exposed_model_name": "arena-right"},
                {"persistent_index": 3, "status": "idle", "exposed_model_name": "arena-left"},
            ]

        def get_tabs_with_index(self):
            return list(self.tabs)

    class FakeBrowser:
        tab_pool = FakePool()

    with tab_routes._route_round_robin_lock:
        tab_routes._route_round_robin_cursor.clear()

    first = tab_routes._resolve_target_tab(FakeBrowser(), model_name="arena-left", selector="round_robin")
    second = tab_routes._resolve_target_tab(FakeBrowser(), model_name="arena-left", selector="round_robin")

    assert first["persistent_index"] == 1
    assert second["persistent_index"] == 3


def test_tab_pool_exposed_model_name_override_precedence():
    manager = TabPoolManager.__new__(TabPoolManager)
    manager.model_name_overrides = {
        "sites": {"arena.ai": "arena-site"},
        "urls": {"https://arena.ai/c/abc": "arena-url"},
    }
    info = {
        "id": "arena_1",
        "current_domain": "arena.ai",
        "route_domain": "arena.ai",
        "url": "https://arena.ai/c/abc",
        "model_name_override": "",
    }

    manager._apply_exposed_model_name(info)
    assert info["exposed_model_name"] == "arena-url"
    assert info["model_name_override_source"] == "url"

    info["model_name_override"] = "arena-temp"
    manager._apply_exposed_model_name(info)
    assert info["exposed_model_name"] == "arena-temp"
    assert info["model_name_override_source"] == "tab"


def test_model_name_overrides_are_written_to_local_file(tmp_path, monkeypatch):
    target = tmp_path / "model_name_overrides.local.json"
    monkeypatch.setattr(tab_routes, "MODEL_NAME_OVERRIDES_PATH", target)

    written = tab_routes._write_model_name_overrides_unlocked(
        {
            "sites": {"Arena.AI": "arena-site"},
            "urls": {"https://arena.ai/c/abc": "arena-url"},
        }
    )

    assert target.exists()
    assert written == {
        "sites": {"arena.ai": "arena-site"},
        "urls": {"https://arena.ai/c/abc": "arena-url"},
    }
    assert tab_routes._read_model_name_overrides_unlocked() == written


def test_global_model_list_uses_exposed_names_without_legacy_defaults(monkeypatch):
    class FakePool:
        def get_tabs_with_index(self):
            return [
                {
                    "id": "arena_1",
                    "persistent_index": 1,
                    "current_domain": "arena.ai",
                    "route_domain": "arena.ai",
                    "exposed_model_name": "Fable5",
                    "model_name_override_source": "tab",
                }
            ]

    class FakeBrowser:
        tab_pool = FakePool()

    monkeypatch.setattr(chat, "get_browser", lambda auto_connect=False: FakeBrowser())

    ids = [item["id"] for item in chat._collect_model_entries()]

    assert ids == ["Fable5"]
    assert "claude-web-browser" not in ids
    assert "web-browser" not in ids


def test_global_model_list_keeps_single_fallback_without_tabs(monkeypatch):
    class FakePool:
        def get_tabs_with_index(self):
            return []

    class FakeBrowser:
        tab_pool = FakePool()

    monkeypatch.setattr(chat, "get_browser", lambda auto_connect=False: FakeBrowser())

    ids = [item["id"] for item in chat._collect_model_entries()]

    assert ids == ["web-browser"]
