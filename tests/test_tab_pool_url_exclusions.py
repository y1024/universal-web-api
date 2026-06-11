import copy
import asyncio

from app.api import tab_routes


class DummyTabPool:
    def __init__(self, tabs=None, excluded_urls=None):
        self._tabs = tabs or []
        self.excluded_urls = excluded_urls or []
        self.runtime_updates = []

    def get_tabs_with_index(self):
        return copy.deepcopy(self._tabs)

    def apply_runtime_config(self, **kwargs):
        self.runtime_updates.append(copy.deepcopy(kwargs))
        if "excluded_urls" in kwargs:
            self.excluded_urls = list(kwargs["excluded_urls"])
        return kwargs


class DummyBrowser:
    def __init__(self, tab_pool):
        self.tab_pool = tab_pool


def test_list_candidate_tabs_filters_domain_excluded_urls():
    browser = DummyBrowser(
        DummyTabPool(
            tabs=[
                {
                    "persistent_index": 1,
                    "current_domain": "chatgpt.com",
                    "url": "https://chatgpt.com/",
                },
                {
                    "persistent_index": 2,
                    "current_domain": "chatgpt.com",
                    "url": "https://chatgpt.com/c/private-chat",
                },
                {
                    "persistent_index": 3,
                    "current_domain": "example.com",
                    "url": "https://example.com/",
                },
            ],
            excluded_urls=["https://chatgpt.com/c/private-chat"],
        )
    )

    candidates = tab_routes._list_candidate_tabs(browser, "chatgpt.com")

    assert [item["persistent_index"] for item in candidates] == [1]


def test_update_tab_pool_config_preserves_excluded_urls_when_omitted(monkeypatch):
    stored_config = {
        "tab_pool": {
            "allocation_mode": "round_robin",
            "enabled_route_methods": ["domain", "fixed_tab"],
            "excluded_urls": ["https://chatgpt.com/c/private-chat"],
        }
    }
    writes = []
    tab_pool = DummyTabPool(excluded_urls=list(stored_config["tab_pool"]["excluded_urls"]))

    monkeypatch.setattr(tab_routes, "_read_browser_config", lambda: copy.deepcopy(stored_config))
    monkeypatch.setattr(
        tab_routes,
        "_write_browser_config_unlocked",
        lambda payload: writes.append(copy.deepcopy(payload)),
    )
    monkeypatch.setattr(tab_routes, "get_browser", lambda auto_connect=False: DummyBrowser(tab_pool))

    result = asyncio.run(
        tab_routes.update_tab_pool_config(
            tab_routes.TabPoolConfigRequest(
                allocation_mode="random",
                enabled_route_methods=["fixed_tab"],
            ),
            authenticated=True,
        ),
    )

    assert writes[0]["tab_pool"]["excluded_urls"] == ["https://chatgpt.com/c/private-chat"]
    assert tab_pool.runtime_updates == [{"allocation_mode": "random"}]
    assert result["excluded_urls"] == ["https://chatgpt.com/c/private-chat"]


def test_update_tab_pool_config_normalizes_explicit_excluded_urls(monkeypatch):
    stored_config = {
        "tab_pool": {
            "allocation_mode": "first_idle",
            "enabled_route_methods": ["domain"],
            "excluded_urls": ["https://old.example.com/chat"],
        }
    }
    writes = []
    tab_pool = DummyTabPool(excluded_urls=list(stored_config["tab_pool"]["excluded_urls"]))

    monkeypatch.setattr(tab_routes, "_read_browser_config", lambda: copy.deepcopy(stored_config))
    monkeypatch.setattr(
        tab_routes,
        "_write_browser_config_unlocked",
        lambda payload: writes.append(copy.deepcopy(payload)),
    )
    monkeypatch.setattr(tab_routes, "get_browser", lambda auto_connect=False: DummyBrowser(tab_pool))

    result = asyncio.run(
        tab_routes.update_tab_pool_config(
            tab_routes.TabPoolConfigRequest(
                allocation_mode="round_robin",
                enabled_route_methods=["domain", "exact_url"],
                excluded_urls=[
                    " https://chatgpt.com/c/private-chat ",
                    "",
                    "https://chatgpt.com/c/private-chat",
                ],
            ),
            authenticated=True,
        ),
    )

    expected = ["https://chatgpt.com/c/private-chat"]
    assert writes[0]["tab_pool"]["excluded_urls"] == expected
    assert tab_pool.runtime_updates == [
        {"allocation_mode": "round_robin", "excluded_urls": expected}
    ]
    assert result["excluded_urls"] == expected
