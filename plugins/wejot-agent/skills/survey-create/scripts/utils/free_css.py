"""base-free.css 注入。"""

from __future__ import annotations

from .assets import read_asset

BASE_FREE_CSS_MARKER = "默认脚手架样式"
BASE_FREE_CSS = read_asset("base-free.css")


def read_base_free_css() -> str:
    return BASE_FREE_CSS


def base_free_css_prefix(css_content: str) -> str:
    if BASE_FREE_CSS and BASE_FREE_CSS_MARKER not in css_content:
        return BASE_FREE_CSS + "\n\n"
    return ""
