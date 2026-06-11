import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMAND_ENGINE = PROJECT_ROOT / "app" / "services" / "command_engine.py"


def _page_check_js_blocks() -> dict[str, str]:
    tree = ast.parse(COMMAND_ENGINE.read_text(encoding="utf-8"))
    blocks: dict[str, str] = {}

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "CommandEngine":
            continue
        for item in node.body:
            if not isinstance(item, ast.Assign) or not isinstance(item.value, ast.Constant):
                continue
            if not isinstance(item.value.value, str):
                continue
            for target in item.targets:
                if isinstance(target, ast.Name) and target.id in {
                    "_PAGE_CHECK_OBSERVER_JS",
                    "_PAGE_CHECK_SNAPSHOT_JS",
                }:
                    blocks[target.id] = item.value.value

    assert set(blocks) == {"_PAGE_CHECK_OBSERVER_JS", "_PAGE_CHECK_SNAPSHOT_JS"}
    return blocks


def test_page_check_js_skips_script_style_and_bulk_text_content():
    for js in _page_check_js_blocks().values():
        assert "function collectText" in js
        assert "node.nodeType === 3" in js
        assert "root.innerText" not in js
        assert "root.textContent" not in js
        for tag in ("SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "META", "HEAD"):
            assert f"tag === '{tag}'" in js


def test_page_check_captcha_selectors_require_visibility():
    for js in _page_check_js_blocks().values():
        assert "function isElementVisible" in js
        assert "function hasVisibleSelector" in js
        assert "hasSelector(" not in js
        assert 'hasVisibleSelector(\'iframe[src*="recaptcha"]\')' in js
        assert 'hasVisibleSelector(\'iframe[src*="challenges.cloudflare.com"]\')' in js
