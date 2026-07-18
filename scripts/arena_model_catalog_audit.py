"""Audit and repair Arena Direct model-name mappings.

Examples:
    python scripts/arena_model_catalog_audit.py
    python scripts/arena_model_catalog_audit.py --fix
    python scripts/arena_model_catalog_audit.py --json --fix
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from DrissionPage import Chromium, ChromiumOptions

from app.services.arena_direct_models import (
    ARENA_MODEL_ALIAS_OVERRIDES_PATH,
    get_arena_direct_model_public_id,
    read_arena_direct_models_from_tab,
)


def _connect_browser(port: int):
    options = ChromiumOptions()
    options.set_address(f"127.0.0.1:{int(port)}")
    options.existing_only()
    return Chromium(addr_or_opts=options)


def _find_arena_tab(browser: Any):
    candidates = []
    for tab in browser.get_tabs():
        url = str(getattr(tab, "url", "") or "").strip()
        if "arena.ai" not in url.lower():
            continue
        candidates.append((0 if "/text/direct" in url else 1, tab))
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1] if candidates else None


def _read_api_models(base_url: str, api_key: str = "") -> List[str]:
    endpoint = f"{base_url.rstrip('/')}/url/arena.ai/models"
    headers = {"Accept": "application/json"}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"
    request = urllib.request.Request(endpoint, headers=headers)
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = payload.get("data") if isinstance(payload, dict) else []
    if not isinstance(data, list):
        return []
    return sorted({str(item.get("id") or "").strip() for item in data if isinstance(item, dict) and str(item.get("id") or "").strip()})


def _build_report(models: List[Dict[str, Any]], api_names: Iterable[str]) -> Dict[str, Any]:
    catalog_names = sorted(
        {
            get_arena_direct_model_public_id(item)
            for item in models
            if get_arena_direct_model_public_id(item)
        }
    )
    api_name_set = {str(name).strip() for name in api_names if str(name).strip()}
    mapping_rows = []
    for model in sorted(models, key=lambda item: str(item.get("name") or "").casefold()):
        name = str(model.get("name") or "").strip()
        display_name = str(model.get("display_name") or "").strip()
        public_name = str(model.get("public_name") or "").strip()
        search_name = str(model.get("search_name") or display_name or public_name or name).strip()
        public_id = get_arena_direct_model_public_id(model)
        mapping_rows.append(
            {
                "name": name,
                "public_id": public_id,
                "arena_model_id": str(model.get("arena_model_id") or ""),
                "display_name": display_name,
                "public_name": public_name,
                "search_name": search_name,
                "aliases": list(model.get("aliases") or []),
                "search_name_differs": search_name.casefold() != name.casefold(),
                "api_visible": public_id in api_name_set,
            }
        )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalog_count": len(catalog_names),
        "api_count": len(api_name_set),
        "missing_from_api": sorted(set(catalog_names) - api_name_set),
        "orphaned_in_api": sorted(api_name_set - set(catalog_names)),
        "visible_name_mappings": [row for row in mapping_rows if row["search_name_differs"]],
        "models": mapping_rows,
    }


def _write_alias_overrides(models: List[Dict[str, Any]]) -> Path:
    payload = {
        "version": 1,
        "source": "arena.ai",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "models": {},
    }
    for model in models:
        name = str(model.get("name") or "").strip()
        if not name:
            continue
        payload["models"][name] = {
            "search_name": str(
                model.get("search_name")
                or model.get("display_name")
                or model.get("public_name")
                or name
            ).strip(),
            "aliases": sorted(
                {
                    str(alias).strip()
                    for alias in (model.get("aliases") or [])
                    if str(alias).strip()
                },
                key=str.casefold,
            ),
            "arena_model_id": str(model.get("arena_model_id") or "").strip(),
        }

    target = ARENA_MODEL_ALIAS_OVERRIDES_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def _print_report(report: Dict[str, Any]) -> None:
    print(f"Arena catalog: {report['catalog_count']} models")
    print(f"API catalog:   {report['api_count']} models")
    print(f"Missing API:   {len(report['missing_from_api'])}")
    print(f"Orphaned API:  {len(report['orphaned_in_api'])}")
    mappings = report["visible_name_mappings"]
    print(f"Display-name mappings: {len(mappings)}")
    for row in mappings:
        print(f"  {row['name']}  <= search: {row['search_name']}")
    if report["missing_from_api"]:
        print("Missing model names:")
        for name in report["missing_from_api"]:
            print(f"  {name}")
    if report["orphaned_in_api"]:
        print("API names not present in the page catalog:")
        for name in report["orphaned_in_api"]:
            print(f"  {name}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--base-url", default="http://127.0.0.1:8199")
    parser.add_argument("--fix", action="store_true", help="write local Arena model alias overrides")
    parser.add_argument(
        "--api-key",
        default=os.getenv("AUTH_TOKEN", ""),
        help="service API token; defaults to AUTH_TOKEN from the environment",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="print the full JSON report")
    parser.add_argument("--strict", action="store_true", help="return exit code 1 when a mismatch exists")
    args = parser.parse_args(argv)

    try:
        browser = _connect_browser(args.cdp_port)
        tab = _find_arena_tab(browser)
        if tab is None:
            print("No Arena tab found. Open https://arena.ai/text/direct first.", file=sys.stderr)
            return 2
        models = read_arena_direct_models_from_tab(tab)
        api_names = _read_api_models(args.base_url, args.api_key)
    except Exception as exc:
        print(f"Arena model audit failed: {exc}", file=sys.stderr)
        return 2

    report = _build_report(models, api_names)
    if args.fix:
        target = _write_alias_overrides(models)
        report["fixed_to"] = str(target)
        print(f"Alias overrides written: {target}")
    if args.as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report)

    has_mismatch = bool(report["missing_from_api"] or report["orphaned_in_api"])
    return 1 if args.strict and has_mismatch else 0


if __name__ == "__main__":
    raise SystemExit(main())
