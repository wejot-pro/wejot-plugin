"""读取 scripts/assets 下的静态资源。"""

from __future__ import annotations

import re
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


def read_asset(name: str) -> str:
    try:
        return (ASSETS_DIR / name).read_text(encoding="utf-8")
    except OSError:
        return ""


def asset_inner_js(name: str) -> str:
    """读取被 <script>…</script> 包裹的资源，剥掉外壳返回纯 JS。"""
    raw = read_asset(name)
    m = re.search(r"<script[^>]*>(.*)</script>", raw, re.DOTALL | re.IGNORECASE)
    return (m.group(1) if m else raw).strip()
