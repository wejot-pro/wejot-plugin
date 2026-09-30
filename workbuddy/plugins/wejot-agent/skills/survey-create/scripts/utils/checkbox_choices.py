"""CHECKBOX minChoices / maxChoices 规范化与选项文案一致性校验。"""

from __future__ import annotations

import html as html_lib
import re

DEFAULT_MIN_CHOICES = 1


def _strip_tags(inner: str) -> str:
    """去掉标签并 unescape；保留全部空白（含首尾与连续空格）。"""
    return html_lib.unescape(re.sub(r"<[^>]*>", "", inner or ""))


def _json_opts_sorted(json_q: dict) -> list[dict]:
    opts = list(json_q.get("options") or [])
    return sorted(opts, key=lambda o: int((o or {}).get("sort", 0) or 0))


def _extract_checkbox_labels_excluding_other(region: str) -> list[str]:
    """从 CHECKBOX 题目区域抽取普通选项可见文本（排除 other 与 scale 选项）。"""
    labels: list[str] = []
    for m in re.finditer(r"<(\w+)\b([^>]*\bdata-option\b[^>]*)>(.*?)</\1>", region, re.S | re.I):
        attrs, inner = m.group(2), m.group(3)
        if "data-scale-value" in attrs or "data-option-other" in attrs:
            continue
        labels.append(_strip_tags(inner))
    return labels


def validate_checkbox_option_labels(json_q: dict, region: str, uid: str) -> list[str]:
    """CHECKBOX：普通选项可见文本 ↔ options[].label（按 sort）；other 不进 label 列表。

    文案按原文精确比对，空白差异（多/少空格、换行等）一律判失败。
    """
    errors: list[str] = []
    json_labels = [str(o.get("label", "")) for o in _json_opts_sorted(json_q)]
    html_labels = _extract_checkbox_labels_excluding_other(region)

    if len(json_labels) != len(html_labels):
        errors.append(
            f"{uid} (CHECKBOX) 普通选项数量不一致: json={len(json_labels)}, html={len(html_labels)}"
        )
        return errors

    for i, (jl, hl) in enumerate(zip(json_labels, html_labels), start=1):
        if jl != hl:
            errors.append(
                f"{uid} (CHECKBOX) options[{i}].label 与 HTML 不一致: "
                f"json={jl!r}, html={hl!r}"
            )
    return errors


def checkbox_option_count(
    options: list | None,
    *,
    other_option: bool = False,
    other_enabled: int | bool = False,
) -> int:
    """可选项总数（含 otherOption / otherEnabled 时 +1）。"""
    count = len(options or [])
    if other_option or bool(other_enabled):
        count += 1
    return count


def normalize_checkbox_choices(
    min_choices: int | None,
    max_choices: int | None,
    *,
    option_count: int | None = None,
) -> tuple[int, int]:
    """规范化多选题最少/最多可选数量。

    - minChoices 缺省 → 1
    - maxChoices 缺省 → option_count（无选项数信息时回退为 minChoices）
    - maxChoices < minChoices → maxChoices = minChoices
    """
    min_c = DEFAULT_MIN_CHOICES if min_choices is None else int(min_choices)
    if min_c < DEFAULT_MIN_CHOICES:
        min_c = DEFAULT_MIN_CHOICES
    if max_choices is None:
        if option_count is not None and option_count >= DEFAULT_MIN_CHOICES:
            max_c = int(option_count)
        else:
            max_c = min_c
    else:
        max_c = int(max_choices)
    if max_c < min_c:
        max_c = min_c
    return min_c, max_c
