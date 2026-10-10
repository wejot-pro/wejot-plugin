"""GENERIC chartHtml 结构 + JS 语法校验（spec 草稿与产物 JSON 共用）。"""

from __future__ import annotations

from typing import Any, Dict, List

from .node_js_check import check_html_script_bodies

TYPE_ALIASES = {
    "GENERIC": "GENERIC",
}


def _paren_hint(raw_err: str) -> str:
    if "Unexpected token ')'" not in raw_err:
        return ""
    if "new Chart" in raw_err or "Chart(" in raw_err:
        return "（提示：常见原因是 Chart 配置对象少写或多写了 `}`，请核对括号配对）"
    return "（提示：请核对 `()` / `{}` 括号配对）"


def question_context_label(q: Dict[str, Any], *, fallback_index: int | None = None) -> str:
    """题目报错定位标签：有 uuid 用 uuid，否则用 code；都没有再用下标兜底。"""
    uuid = str(q.get("uuid") or "").strip()
    if uuid:
        return f"题目 {uuid}"
    code = str(q.get("code") or "").strip()
    if code:
        return f"题目 code={code}"
    if fallback_index is not None:
        return f"题目(下标 {fallback_index})"
    return "题目(未知标识)"


def validate_chart_html_fragment(chart_html: str, *, context: str) -> List[str]:
    """校验单段 chartHtml：结构快检 + script 语法。"""
    errors: List[str] = []
    text = str(chart_html or "")
    if not text.strip():
        errors.append(f"{context}: chartHtml 不能为空")
        return errors

    missing: List[str] = []
    if "chart-content" not in text:
        missing.append("#chart-content（或字面量 chart-content）")
    if "renderChart" not in text:
        missing.append("window.renderChart")
    if missing:
        errors.append(f"{context}: chartHtml 缺少 {' / '.join(missing)}")
        return errors

    js_errors, _node_skipped = check_html_script_bodies(text, label=context)
    for err in js_errors:
        hint = _paren_hint(err)
        errors.append(f"{err}{hint}")
    return errors


def validate_spec_questions_chart_html(questions: List[Any]) -> List[str]:
    """校验 spec.questions 中 GENERIC 题的 chartHtml。"""
    errors: List[str] = []
    if not isinstance(questions, list):
        return errors

    for idx, q in enumerate(questions, start=1):
        if not isinstance(q, dict):
            continue
        qtype = TYPE_ALIASES.get(str(q.get("type", "")).upper(), str(q.get("type", "")).upper())
        if qtype != "GENERIC":
            continue
        context = question_context_label(q, fallback_index=idx)
        errors.extend(validate_chart_html_fragment(str(q.get("chartHtml", "")), context=context))
    return errors


def validate_schema_generic_chart_html(schema: Dict[str, Any]) -> List[str]:
    """校验 question_schema JSON 中 genericQuestions[].chartHtml。"""
    errors: List[str] = []
    generic = schema.get("genericQuestions") or []
    if not isinstance(generic, list):
        return errors

    for i, q in enumerate(generic, start=1):
        if not isinstance(q, dict):
            continue
        context = question_context_label(q, fallback_index=i)
        errors.extend(validate_chart_html_fragment(str(q.get("chartHtml", "")), context=context))
    return errors
