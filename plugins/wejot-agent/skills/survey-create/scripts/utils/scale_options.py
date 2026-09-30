"""SCALE 选项分值/文案一致性校验（标准模式 HTML ↔ JSON schema）。"""

from __future__ import annotations

import html as html_lib
import re
from typing import Any


def _strip_tags(inner: str) -> str:
    """去掉标签并 unescape；保留全部空白（含首尾与连续空格）。"""
    return html_lib.unescape(re.sub(r"<[^>]*>", "", inner or ""))


def _format_data_scale_value(score: Any) -> str:
    """与 generate_standard_survey._format_data_scale_value 对齐。"""
    if isinstance(score, bool):
        return str(score)
    if isinstance(score, int) and not isinstance(score, bool):
        return str(score)
    if isinstance(score, float):
        if score == int(score):
            return str(int(score))
        return str(score).rstrip("0").rstrip(".") if "." in str(score) else str(score)
    return str(score).strip()


def _json_opts_sorted(json_q: dict) -> list[dict]:
    opts = list(json_q.get("options") or [])
    return sorted(opts, key=lambda o: int((o or {}).get("sort", 0) or 0))


def _extract_scale_points(region: str) -> list[tuple[str, str]]:
    """SCALE：[(data-scale-value, title_text), ...] 按 DOM 顺序。"""
    out: list[tuple[str, str]] = []
    for m in re.finditer(
        r"<div\b(?=[^>]*\bdata-option\b)(?=[^>]*\bdata-scale-value=)[^>]*>(.*?)</div>",
        region,
        re.S | re.I,
    ):
        open_tag = region[m.start() : m.start(1)]
        sm = re.search(r'data-scale-value="([^"]*)"', open_tag, re.I)
        if not sm:
            continue
        out.append((sm.group(1), _strip_tags(m.group(1))))
    return out


def validate_scale_option_points(json_q: dict, region: str, uid: str) -> list[str]:
    """SCALE：data-scale-value↔score，可见文本↔title。

    文案按原文精确比对，空白差异一律判失败。
    """
    errors: list[str] = []
    json_opts = _json_opts_sorted(json_q)
    html_pts = _extract_scale_points(region)

    if len(json_opts) != len(html_pts):
        errors.append(
            f"{uid} (SCALE) 刻度数量不一致: json={len(json_opts)}, html={len(html_pts)}"
        )
        return errors

    for i, (jo, (hs, ht)) in enumerate(zip(json_opts, html_pts), start=1):
        expect_score = _format_data_scale_value(jo.get("score"))
        expect_title = str(jo.get("title", ""))
        if hs != expect_score:
            errors.append(
                f"{uid} (SCALE) options[{i}].score 与 data-scale-value 不一致: "
                f"json={expect_score!r}, html={hs!r}"
            )
        if ht != expect_title:
            errors.append(
                f"{uid} (SCALE) options[{i}].title 与 HTML 不一致: "
                f"json={expect_title!r}, html={ht!r}"
            )
    return errors
