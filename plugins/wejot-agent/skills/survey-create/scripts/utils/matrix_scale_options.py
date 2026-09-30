"""MATRIX_SCALE 行/列选项一致性校验（标准模式 HTML ↔ JSON schema）。"""

from __future__ import annotations

import html as html_lib
import re
from typing import Any


def _html_unescape_text(s: str) -> str:
    """仅 unescape；保留全部空白。"""
    return html_lib.unescape(s or "")


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


def _json_rows_sorted(json_q: dict) -> list[dict]:
    rows = list(json_q.get("rows") or [])
    return sorted(rows, key=lambda r: int((r or {}).get("sort", 0) or 0))


def _json_cols_sorted(json_q: dict) -> list[dict]:
    cols = list(json_q.get("columns") or [])
    return sorted(cols, key=lambda c: int((c or {}).get("sort", 0) or 0))


def _row_title(row: dict) -> str:
    return str(row.get("rowTitle") or row.get("title") or row.get("label") or "")


def _col_title(col: dict) -> str:
    return str(col.get("columnTitle") or col.get("title") or "")


def _extract_matrix_rows(region: str) -> list[str]:
    return re.findall(r'\bdata-matrix-row-label="([^"]*)"', region, re.I)


def _extract_matrix_header_columns(region: str) -> list[tuple[str, str]]:
    """从 matrix-header 抽列：[(score, columnTitle), ...]。"""
    hm = re.search(
        r'data-survey-role="matrix-header"[^>]*>(.*?)(?:data-survey-role="matrix-scroll"|$)',
        region,
        re.S | re.I,
    )
    header = hm.group(1) if hm else region
    out: list[tuple[str, str]] = []
    for m in re.finditer(
        r'<div\b([^>]*\bdata-matrix-column\b[^>]*)>(.*?)</div>',
        header,
        re.S | re.I,
    ):
        attrs, inner = m.group(1), m.group(2)
        sm = re.search(r'data-scale-value="([^"]*)"', attrs, re.I)
        if not sm:
            continue
        tm = re.search(r'class="[^"]*matrix-column-text[^"]*"[^>]*>(.*?)</', inner, re.S | re.I)
        title = _strip_tags(tm.group(1) if tm else inner)
        out.append((sm.group(1), title))
    return out


def validate_matrix_scale_options(json_q: dict, region: str, uid: str) -> list[str]:
    """MATRIX：rows↔data-matrix-row-label；columns↔header data-matrix-column。

    文案按原文精确比对，空白差异一律判失败。
    """
    errors: list[str] = []
    j_rows = _json_rows_sorted(json_q)
    h_rows = [_html_unescape_text(x) for x in _extract_matrix_rows(region)]
    expect_rows = [_row_title(r) for r in j_rows]

    if len(expect_rows) != len(h_rows):
        errors.append(
            f"{uid} (MATRIX) 行数不一致: json={len(expect_rows)}, html={len(h_rows)}"
        )
    else:
        for i, (jr, hr) in enumerate(zip(expect_rows, h_rows), start=1):
            if jr != hr:
                errors.append(
                    f"{uid} (MATRIX) rows[{i}] 与 data-matrix-row-label 不一致: "
                    f"json={jr!r}, html={hr!r}"
                )

    j_cols = _json_cols_sorted(json_q)
    h_cols = _extract_matrix_header_columns(region)
    if len(j_cols) != len(h_cols):
        errors.append(
            f"{uid} (MATRIX) 列数不一致: json={len(j_cols)}, html={len(h_cols)}"
        )
    else:
        for i, (jc, (hs, ht)) in enumerate(zip(j_cols, h_cols), start=1):
            expect_score = _format_data_scale_value(jc.get("score"))
            expect_title = _col_title(jc)
            if hs != expect_score:
                errors.append(
                    f"{uid} (MATRIX) columns[{i}].score 与 data-scale-value 不一致: "
                    f"json={expect_score!r}, html={hs!r}"
                )
            if ht != expect_title:
                errors.append(
                    f"{uid} (MATRIX) columns[{i}].columnTitle 与 HTML 不一致: "
                    f"json={expect_title!r}, html={ht!r}"
                )
    return errors
