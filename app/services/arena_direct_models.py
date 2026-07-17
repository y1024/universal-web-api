"""Read Arena Direct's model catalog from the already-loaded page state."""

from __future__ import annotations

import copy
import threading
import time
from typing import Any, Dict, List, Optional

from app.core.config import logger
from app.utils.site_url import extract_remote_site_domain


ARENA_DIRECT_MODEL_PREFIX = "arena.ai/direct/"
ARENA_DIRECT_MODEL_CACHE_TTL = 300.0


_ARENA_DIRECT_MODEL_EXTRACT_JS = r"""
return (() => {
    const readArray = (text, marker) => {
        const markerIndex = text.indexOf(marker);
        if (markerIndex < 0) return null;
        const start = text.indexOf('[', markerIndex + marker.length);
        if (start < 0) return null;

        let depth = 0;
        let quoted = false;
        let escaped = false;
        for (let index = start; index < text.length; index += 1) {
            const char = text[index];
            if (quoted) {
                if (escaped) escaped = false;
                else if (char === '\\') escaped = true;
                else if (char === '"') quoted = false;
                continue;
            }
            if (char === '"') quoted = true;
            else if (char === '[') depth += 1;
            else if (char === ']') {
                depth -= 1;
                if (depth === 0) return text.slice(start, index + 1);
            }
        }
        return null;
    };

    const payloadTexts = [];
    for (const script of document.scripts) {
        const source = String(script.textContent || '').trim();
        const prefix = 'self.__next_f.push(';
        if (!source.startsWith(prefix) || !source.endsWith(')')) continue;
        try {
            const payload = JSON.parse(source.slice(prefix.length, -1));
            if (Array.isArray(payload) && typeof payload[1] === 'string') {
                payloadTexts.push(payload[1]);
            }
        } catch (_) {}
    }

    for (const text of payloadTexts) {
        const rawModels = readArray(text, '"initialModels":');
        if (!rawModels) continue;
        try {
            const models = JSON.parse(rawModels);
            const seenNames = new Set();
            return models.filter((model) => {
                if (!model || model.userSelectable === false) return false;
                if (!model.id || !model.name || seenNames.has(model.name)) return false;
                const input = model.capabilities && model.capabilities.inputCapabilities;
                const output = model.capabilities && model.capabilities.outputCapabilities;
                if (!input || input.text !== true || !output || output.text !== true) return false;
                if (!model.rankByModality || !Number.isFinite(model.rankByModality.chat)) return false;
                seenNames.add(model.name);
                return true;
            }).map((model) => ({
                arena_model_id: String(model.id),
                name: String(model.name),
                public_name: String(model.publicName || model.displayName || model.name),
                display_name: String(model.displayName || model.publicName || model.name),
                provider: String(model.provider || ''),
                organization: String(model.organization || model.provider || 'arena.ai')
            }));
        } catch (_) {
            return [];
        }
    }
    return [];
})();
"""


_cache_lock = threading.RLock()
_refresh_lock = threading.Lock()
_cached_at = 0.0
_cached_models: List[Dict[str, Any]] = []


def build_arena_direct_model_id(arena_model_id: Any) -> str:
    clean_id = str(arena_model_id or "").strip()
    return f"{ARENA_DIRECT_MODEL_PREFIX}{clean_id}" if clean_id else ""


def parse_arena_direct_model_id(model_id: Any) -> str:
    value = str(model_id or "").strip()
    if not value.lower().startswith(ARENA_DIRECT_MODEL_PREFIX):
        return ""
    return value[len(ARENA_DIRECT_MODEL_PREFIX):].strip()


def is_arena_direct_model_id(model_id: Any) -> bool:
    return bool(parse_arena_direct_model_id(model_id))


def _normalize_models(raw_models: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_models, list):
        return []

    normalized: List[Dict[str, Any]] = []
    seen_ids = set()
    seen_names = set()
    for raw in raw_models:
        if not isinstance(raw, dict):
            continue
        arena_model_id = str(raw.get("arena_model_id") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not arena_model_id or not name:
            continue
        id_key = arena_model_id.lower()
        name_key = name.lower()
        if id_key in seen_ids or name_key in seen_names:
            continue
        seen_ids.add(id_key)
        seen_names.add(name_key)
        public_name = str(raw.get("public_name") or raw.get("display_name") or name).strip()
        display_name = str(raw.get("display_name") or public_name or name).strip()
        normalized.append(
            {
                "arena_model_id": arena_model_id,
                "name": name,
                "public_name": public_name or name,
                "display_name": display_name or public_name or name,
                "provider": str(raw.get("provider") or "").strip(),
                "organization": str(raw.get("organization") or raw.get("provider") or "arena.ai").strip(),
            }
        )
    return normalized


def read_arena_direct_models_from_tab(tab: Any) -> List[Dict[str, Any]]:
    try:
        return _normalize_models(tab.run_js(_ARENA_DIRECT_MODEL_EXTRACT_JS, timeout=3.0))
    except TypeError:
        return _normalize_models(tab.run_js(_ARENA_DIRECT_MODEL_EXTRACT_JS))


def _cache_snapshot() -> tuple[float, List[Dict[str, Any]]]:
    with _cache_lock:
        return _cached_at, copy.deepcopy(_cached_models)


def _replace_cache(models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    global _cached_at, _cached_models
    normalized = _normalize_models(models)
    if not normalized:
        return []
    with _cache_lock:
        _cached_at = time.monotonic()
        _cached_models = copy.deepcopy(normalized)
    return copy.deepcopy(normalized)


def _session_is_idle(session: Any) -> bool:
    status = str(getattr(getattr(session, "status", None), "value", "") or "").strip().lower()
    return status in {"", "idle"}


def _arena_sessions(browser: Any) -> List[Any]:
    try:
        sessions = browser.tab_pool.get_sessions_snapshot()
    except Exception:
        return []

    result = []
    for session in sessions or []:
        try:
            current_url, _domain = session.get_cached_route_snapshot()
        except Exception:
            current_url = str(getattr(getattr(session, "tab", None), "url", "") or "")
        if extract_remote_site_domain(current_url) != "arena.ai":
            continue
        result.append(session)
    result.sort(key=lambda item: (not _session_is_idle(item), int(getattr(item, "persistent_index", 0) or 0)))
    return result


def list_arena_direct_models(browser: Any, *, force: bool = False) -> List[Dict[str, Any]]:
    cached_at, cached = _cache_snapshot()
    if cached and not force and time.monotonic() - cached_at < ARENA_DIRECT_MODEL_CACHE_TTL:
        return cached

    if not _refresh_lock.acquire(blocking=False):
        return cached
    try:
        cached_at, cached = _cache_snapshot()
        if cached and not force and time.monotonic() - cached_at < ARENA_DIRECT_MODEL_CACHE_TTL:
            return cached

        for session in _arena_sessions(browser):
            if not _session_is_idle(session):
                continue
            try:
                models = read_arena_direct_models_from_tab(session.tab)
            except Exception as exc:
                logger.debug(f"Arena Direct 模型目录读取失败（尝试下一标签页）: {exc}")
                continue
            if models:
                logger.info(f"Arena Direct 模型目录已刷新: {len(models)} 个文本模型")
                return _replace_cache(models)
        return cached
    finally:
        _refresh_lock.release()


def resolve_arena_direct_model(tab: Any, requested_model: Any) -> Optional[Dict[str, Any]]:
    arena_model_id = parse_arena_direct_model_id(requested_model)
    if not arena_model_id:
        return None

    _cached_at_value, cached = _cache_snapshot()
    for model in cached:
        if model["arena_model_id"].lower() == arena_model_id.lower():
            return model

    models = read_arena_direct_models_from_tab(tab)
    if models:
        _replace_cache(models)
    for model in models:
        if model["arena_model_id"].lower() == arena_model_id.lower():
            return model
    return None


def build_openai_model_entries(models: List[Dict[str, Any]], *, created: int) -> List[Dict[str, Any]]:
    entries = []
    for model in models or []:
        model_id = build_arena_direct_model_id(model.get("arena_model_id"))
        if not model_id:
            continue
        entries.append(
            {
                "id": model_id,
                "object": "model",
                "type": "model",
                "created": created,
                "owned_by": model.get("organization") or model.get("provider") or "arena.ai",
                "display_name": f"Arena Direct · {model.get('display_name') or model.get('public_name') or model.get('name')}",
            }
        )
    return entries


__all__ = [
    "ARENA_DIRECT_MODEL_PREFIX",
    "build_arena_direct_model_id",
    "build_openai_model_entries",
    "is_arena_direct_model_id",
    "list_arena_direct_models",
    "parse_arena_direct_model_id",
    "read_arena_direct_models_from_tab",
    "resolve_arena_direct_model",
]
