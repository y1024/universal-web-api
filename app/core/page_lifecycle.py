"""Best-effort helpers for keeping background tabs logically active.

These helpers avoid stealing OS/browser foreground focus while reducing the
chance that background visibility checks pause site scripts.
"""

from __future__ import annotations

from typing import Any

from app.core.config import logger


_VISIBILITY_EMULATION_SOURCE = r"""
(function() {
  try {
    const W = window;
    const D = document;
    const firstInstall = !Object.prototype.hasOwnProperty.call(D, "hidden")
      && !Object.prototype.hasOwnProperty.call(D, "visibilityState");

    const define = (target, name, descriptor) => {
      try {
        Object.defineProperty(target, name, descriptor);
        return true;
      } catch (error) {
        return false;
      }
    };
    const defineGetter = (target, name, value) => define(target, name, {
      configurable: true,
      enumerable: true,
      get: () => value,
    });
    const defineValue = (target, name, value) => define(target, name, {
      configurable: true,
      enumerable: true,
      writable: true,
      value,
    });

    defineGetter(D, "hidden", false);
    defineGetter(D, "visibilityState", "visible");
    defineGetter(D, "webkitHidden", false);
    defineGetter(D, "webkitVisibilityState", "visible");
    defineGetter(D, "wasDiscarded", false);
    defineGetter(D, "prerendering", false);
    defineValue(D, "hasFocus", function() { return true; });

    defineValue(W, "focus", function() {
      try { W.dispatchEvent(new Event("focus")); } catch (error) {}
      return undefined;
    });
    defineValue(W, "blur", function() { return undefined; });

    if (firstInstall) {
      try { D.dispatchEvent(new Event("visibilitychange")); } catch (error) {}
      try { W.dispatchEvent(new Event("focus")); } catch (error) {}
    }
  } catch (error) {
    try {
      window.__codexVisibilityEmulationErrorV1 = String(error && error.message ? error.message : error || "");
    } catch (e) {}
  }
})();
""".strip()


def install_visibility_emulation(tab: Any, owner: Any = None, *, reason: str = "") -> bool:
    """Best-effort patch for visibility/focus APIs on the current tab."""
    if tab is None:
        return False

    source = _VISIBILITY_EMULATION_SOURCE
    owner_attr = "_codex_visibility_emulation_source"
    script_id_attr = "_codex_visibility_emulation_script_id"

    if owner is not None and getattr(owner, owner_attr, None) != source:
        try:
            result = tab.run_cdp("Page.addScriptToEvaluateOnNewDocument", source=source)
            setattr(owner, owner_attr, source)
            script_id = ""
            if isinstance(result, dict):
                script_id = (
                    result.get("identifier")
                    or result.get("scriptId")
                    or result.get("id")
                    or ""
                )
            elif isinstance(result, (str, int, float)):
                script_id = str(result)
            if script_id:
                setattr(owner, script_id_attr, str(script_id))
        except Exception as e:
            logger.debug_throttled(
                "page_wake.visibility.install",
                f"[PAGE_WAKE] 预注入可见性模拟失败（忽略）: reason={reason or '-'}, error={e}",
                interval_sec=10.0,
            )

    try:
        tab.run_js(source)
    except Exception as e:
        logger.debug_throttled(
            "page_wake.visibility.apply",
            f"[PAGE_WAKE] 当前页可见性模拟失败（忽略）: reason={reason or '-'}, error={e}",
            interval_sec=10.0,
        )
        return False

    try:
        state = tab.run_js(
            "return {hidden: !!document.hidden, visibilityState: document.visibilityState || '', hasFocus: !!(document.hasFocus && document.hasFocus()), wasDiscarded: !!document.wasDiscarded};"
        )
        if isinstance(state, dict):
            return (state.get("hidden") is False) and (str(state.get("visibilityState") or "").lower() == "visible")
        return False
    except Exception:
        return False


_VISIBILITY_EMULATION_RESTORE_SOURCE = r"""
(function() {
  try {
    const W = window;
    const D = document;

    try { delete D.hidden; } catch (error) {}
    try { delete D.visibilityState; } catch (error) {}
    try { delete D.webkitHidden; } catch (error) {}
    try { delete D.webkitVisibilityState; } catch (error) {}
    try { delete D.wasDiscarded; } catch (error) {}
    try { delete D.prerendering; } catch (error) {}
    try { delete D.hasFocus; } catch (error) {}

    try { delete W.focus; } catch (error) {}
    try { delete W.blur; } catch (error) {}
    try { delete W.__codexVisibilityEmulationErrorV1; } catch (error) {}

    try { D.dispatchEvent(new Event("visibilitychange")); } catch (error) {}
    try { W.dispatchEvent(new Event("focus")); } catch (error) {}
  } catch (error) {}
})();
""".strip()


def restore_visibility_emulation(tab: Any, owner: Any = None, *, reason: str = "") -> bool:
    """Best-effort restore for visibility/focus API overrides."""
    if tab is None:
        return False

    if owner is not None:
        script_id_attr = "_codex_visibility_emulation_script_id"
        script_id = str(getattr(owner, script_id_attr, "") or "").strip()
        if script_id:
            try:
                tab.run_cdp(
                    "Page.removeScriptToEvaluateOnNewDocument",
                    identifier=script_id,
                )
            except Exception:
                pass
            try:
                delattr(owner, script_id_attr)
            except Exception:
                pass
        try:
            delattr(owner, "_codex_visibility_emulation_source")
        except Exception:
            pass

    try:
        tab.run_js(_VISIBILITY_EMULATION_RESTORE_SOURCE)
        return True
    except Exception as e:
        logger.debug_throttled(
            "page_wake.visibility.restore",
            f"[PAGE_WAKE] 可见性模拟恢复失败（忽略）: reason={reason or '-'}, error={e}",
            interval_sec=10.0,
        )
        return False
