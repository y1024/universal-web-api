from app.api.cmd_routes import _idle_tabs_for_manual_command
from app.core.tab_pool_parts.session import TabStatus


class FakeSession:
    def __init__(self, session_id, persistent_index, url, status=TabStatus.IDLE):
        self.id = session_id
        self.persistent_index = persistent_index
        self.url = url
        self.status = status

    def get_cached_route_snapshot(self):
        return self.url, "arena.ai"


class SnapshotPool:
    def __init__(self, sessions, excluded_url):
        self.sessions = sessions
        self.excluded_url = excluded_url

    def get_sessions_snapshot(self):
        return self.sessions

    def is_url_excluded(self, url):
        return str(url or "") == self.excluded_url


class StatusOnlyPool:
    def __init__(self, tabs, excluded_url):
        self.tabs = tabs
        self.excluded_url = excluded_url

    def get_status(self):
        return {"tabs": self.tabs}

    def is_url_excluded(self, url):
        return str(url or "") == self.excluded_url


def test_manual_command_idle_candidates_skip_route_excluded_snapshot_sessions():
    pool = SnapshotPool(
        [
            FakeSession("arena_1", 1, "https://arena.ai/c/excluded"),
            FakeSession("arena_2", 2, "https://arena.ai/c/allowed"),
            FakeSession("arena_3", 3, "https://arena.ai/c/busy", status=TabStatus.BUSY),
        ],
        excluded_url="https://arena.ai/c/excluded",
    )

    candidates = _idle_tabs_for_manual_command(pool)

    assert [item["tab_index"] for item in candidates] == [2]


def test_manual_command_idle_candidates_skip_route_excluded_status_items():
    pool = StatusOnlyPool(
        [
            {
                "persistent_index": 3,
                "status": "idle",
                "url": "https://arena.ai/c/allowed-later",
            },
            {
                "persistent_index": 1,
                "status": "idle",
                "url": "https://arena.ai/c/excluded",
            },
            {
                "persistent_index": 2,
                "status": "idle",
                "route_excluded": True,
                "url": "https://arena.ai/c/flagged",
            },
        ],
        excluded_url="https://arena.ai/c/excluded",
    )

    candidates = _idle_tabs_for_manual_command(pool)

    assert [item["tab_index"] for item in candidates] == [3]
