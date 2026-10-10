"""向 survey-ui.js / survey-ui.css 注入脚手架片段。"""

from __future__ import annotations

from pathlib import Path

JS_REGION_BEGIN = "/* ===== LLM 自定义交互逻辑区域 BEGIN ===== */"


def replace_fenced_block(content: str, begin_marker: str, end_marker: str, new_block: str) -> str:
    """用 new_block 替换 begin/end 标记之间的内容（含标记本身）。"""
    if begin_marker not in content or end_marker not in content:
        return content
    start = content.index(begin_marker)
    end = content.index(end_marker, start) + len(end_marker)
    return content[:start] + new_block.rstrip() + content[end:]


def inject_js_to_survey_ui(
    work_dir: Path,
    js: str,
    html: str,
    *,
    marker: str,
    replace: bool = False,
    block_begin: str | None = None,
    block_end: str | None = None,
) -> str:
    """优先注入 survey-ui.js LLM 区；legacy fallback 注入 HTML。

    replace=True 且 block_begin/block_end 已存在时，替换整段 fenced 块（可重复跑 generator）。
    """
    js_path = work_dir / "survey-ui.js"
    fenced = block_begin and block_end
    if js_path.is_file():
        js_content = js_path.read_text(encoding="utf-8")
        if JS_REGION_BEGIN in js_content:
            if replace and fenced and block_begin in js_content:
                js_path.write_text(
                    replace_fenced_block(js_content, block_begin, block_end, js),
                    encoding="utf-8",
                )
                return html
            if replace and fenced:
                js_path.write_text(
                    js_content.replace(JS_REGION_BEGIN, JS_REGION_BEGIN + "\n" + js, 1),
                    encoding="utf-8",
                )
                return html
            if marker in js_content:
                return html
            js_path.write_text(js_content.replace(JS_REGION_BEGIN, JS_REGION_BEGIN + "\n" + js, 1), encoding="utf-8")
            return html
    if JS_REGION_BEGIN in html:
        if replace and fenced and block_begin in html:
            return replace_fenced_block(html, block_begin, block_end, js)
        if marker in html:
            return html
        return html.replace(JS_REGION_BEGIN, JS_REGION_BEGIN + "\n" + js, 1)
    if replace and fenced and block_begin in html:
        return replace_fenced_block(html, block_begin, block_end, js)
    if marker in html:
        return html
    return html.replace("</body>", "  <script>\n" + js + "\n  </script>\n</body>", 1)


def append_css_marker(
    work_dir: Path,
    marker: str,
    css_block: str,
    *,
    prefix: str = "",
    replace: bool = False,
    block_end: str | None = None,
) -> None:
    css_path = work_dir / "survey-ui.css"
    if not css_path.is_file():
        raise ValueError(f"未找到 {css_path}，请先运行 generate_free_mode_skeleton.py")
    css_content = css_path.read_text(encoding="utf-8")
    if replace and block_end and marker in css_content and block_end in css_content:
        css_path.write_text(replace_fenced_block(css_content, marker, block_end, css_block), encoding="utf-8")
        return
    if marker in css_content:
        return
    head = prefix + "\n\n" if prefix else ""
    css_path.write_text(head + css_content.rstrip() + "\n\n" + css_block, encoding="utf-8")


def append_js_asset(work_dir: Path, js_content: str, *, fence_marker: str) -> None:
    """在 survey-ui.js 末尾追加套件 JS（防重复）。"""
    js_path = work_dir / "survey-ui.js"
    if not js_path.is_file() or not js_content:
        return
    existing = js_path.read_text(encoding="utf-8")
    if fence_marker in existing:
        return
    js_path.write_text(existing.rstrip() + "\n\n" + js_content + "\n", encoding="utf-8")
