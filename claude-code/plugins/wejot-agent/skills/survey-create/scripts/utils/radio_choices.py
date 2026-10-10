"""RADIO 选项文案一致性校验（标准模式 HTML ↔ JSON schema）。"""

from __future__ import annotations

import html as html_lib
import re


def _strip_tags(inner: str) -> str:
    """去掉标签并 unescape；保留全部空白（含首尾与连续空格）。"""
    return html_lib.unescape(re.sub(r"<[^>]*>", "", inner or ""))


def _json_opts_sorted(json_q: dict) -> list[dict]:
    opts = list(json_q.get("options") or [])
    return sorted(opts, key=lambda o: int((o or {}).get("sort", 0) or 0))


def _extract_radio_labels_excluding_other(region: str) -> list[str]:
    """从 RADIO 题目区域抽取普通选项可见文本（排除 other 与 scale 选项）。"""
    labels: list[str] = []
    for m in re.finditer(r"<(\w+)\b([^>]*\bdata-option\b[^>]*)>(.*?)</\1>", region, re.S | re.I):
        attrs, inner = m.group(2), m.group(3)
        if "data-scale-value" in attrs or "data-option-other" in attrs:
            continue
        labels.append(_strip_tags(inner))
    return labels


def validate_radio_option_labels(json_q: dict, region: str, uid: str) -> list[str]:
    """RADIO：普通选项可见文本 ↔ options[].label（按 sort）；other 不进 label 列表。

    文案按原文精确比对，空白差异（多/少空格、换行等）一律判失败。
    """
    errors: list[str] = []
    json_labels = [str(o.get("label", "")) for o in _json_opts_sorted(json_q)]
    html_labels = _extract_radio_labels_excluding_other(region)

    if len(json_labels) != len(html_labels):
        errors.append(
            f"{uid} (RADIO) 普通选项数量不一致: json={len(json_labels)}, html={len(html_labels)}"
        )
        return errors

    for i, (jl, hl) in enumerate(zip(json_labels, html_labels), start=1):
        if jl != hl:
            errors.append(
                f"{uid} (RADIO) options[{i}].label 与 HTML 不一致: "
                f"json={jl!r}, html={hl!r}"
            )
    return errors
