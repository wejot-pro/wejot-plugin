"""
自由模式问卷校验器。

校验 survey-unified-generate.html 与 question_schema_generate.json 的一致性，
包括 data-* 属性、questionUuid、state.answers 键名、提交函数等。

用法:
    python validate_free_mode_survey.py --schema /path/to/question_schema_generate.json --html /path/to/survey-unified-generate.html

    # 也可单独校验独立的 answers JSON（较少用）
    python validate_free_mode_survey.py --json /path/to/answers.json [--schema /path/to/question_schema_generate.json]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from utils.checkbox_choices import checkbox_option_count, normalize_checkbox_choices
from utils.chart_html_syntax import validate_schema_generic_chart_html
from utils.node_js_check import check_js_file

VALID_TYPES = {
    "RADIO",
    "CHECKBOX",
    "TEXTAREA",
    "SCALE",
    "MATRIX_SCALE",
    "UPLOAD",
    "GENERIC",
}

QUESTION_ARRAY_KEYS = [
    "radioQuestions",
    "checkboxQuestions",
    "textQuestions",
    "uploadQuestions",
    "scaleQuestions",
    "matrixScaleQuestions",
    "genericQuestions",
]


def validate_answers(data: Any) -> List[str]:
    """校验 answers 数组，返回错误列表（空表示通过）。"""
    errors: List[str] = []

    if not isinstance(data, list):
        errors.append("根节点必须是数组")
        return errors

    if len(data) == 0:
        errors.append("answers 数组不能为空")
        return errors

    for idx, item in enumerate(data):
        prefix = f"第 {idx + 1} 题"

        if not isinstance(item, dict):
            errors.append(f"{prefix}: 必须是对象")
            continue

        if "data" not in item:
            errors.append(f"{prefix}: 缺少 'data' 包装层")
            continue

        d = item["data"]
        if not isinstance(d, dict):
            errors.append(f"{prefix}: 'data' 必须是对象")
            continue

        # 必填字段
        if "questionUuid" not in d:
            errors.append(f"{prefix}: 缺少 questionUuid")
        elif not isinstance(d.get("questionUuid"), str) or not d.get("questionUuid"):
            errors.append(f"{prefix}: questionUuid 必须是非空字符串")

        qtype = d.get("questionType")
        if "questionType" not in d:
            errors.append(f"{prefix}: 缺少 questionType")
        elif qtype not in VALID_TYPES:
            errors.append(
                f"{prefix}: questionType '{qtype}' 不合法，"
                f"必须是 {', '.join(sorted(VALID_TYPES))} 之一"
            )

        if qtype in VALID_TYPES:
            errors.extend(_validate_by_type(prefix, qtype, d))

        # 检查非法顶层字段（data 之外）
        for key in item:
            if key != "data":
                errors.append(f"{prefix}: 不允许的顶层字段 '{key}'，只能用 'data'")

    return errors


def _validate_by_type(prefix: str, qtype: str, d: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    if qtype == "RADIO":
        opts = d.get("options")
        if not isinstance(opts, list):
            errors.append(f"{prefix}: RADIO 必须提供 options 数组")
        elif len(opts) != 1:
            errors.append(f"{prefix}: RADIO options 只能有 1 条（选中的那项）")
        else:
            errors.extend(_validate_option(prefix, opts[0]))

    elif qtype == "CHECKBOX":
        opts = d.get("options")
        if not isinstance(opts, list):
            errors.append(f"{prefix}: CHECKBOX 必须提供 options 数组")
        elif len(opts) == 0:
            errors.append(f"{prefix}: CHECKBOX options 不能为空（至少选一项）")
        else:
            for oidx, opt in enumerate(opts):
                errors.extend(_validate_option(f"{prefix} options[{oidx}]", opt))

    elif qtype == "TEXTAREA":
        if "value" not in d:
            errors.append(f"{prefix}: TEXTAREA 必须提供 value")
        if d.get("textId") is not None:
            errors.append(f"{prefix}: TEXTAREA textId 必须为 null")

    elif qtype == "SCALE":
        score = d.get("score")
        if score is None:
            errors.append(f"{prefix}: SCALE 必须提供 score")
        elif not isinstance(score, (int, float)):
            errors.append(f"{prefix}: SCALE score 必须是数字")
        if d.get("scaleId") is not None:
            errors.append(f"{prefix}: SCALE scaleId 必须为 null")

    elif qtype == "MATRIX_SCALE":
        rows = d.get("matrixScaleAnswers")
        if not isinstance(rows, list) or len(rows) == 0:
            errors.append(f"{prefix}: MATRIX_SCALE 必须提供非空 matrixScaleAnswers 数组")
        else:
            for ridx, row in enumerate(rows):
                rp = f"{prefix} matrixScaleAnswers[{ridx}]"
                if not isinstance(row, dict):
                    errors.append(f"{rp}: 必须是对象")
                    continue
                if "rowTitle" not in row:
                    errors.append(f"{rp}: 缺少 rowTitle")
                if "score" not in row:
                    errors.append(f"{rp}: 缺少 score")
                elif not isinstance(row.get("score"), (int, float)):
                    errors.append(f"{rp}: score 必须是数字")

    elif qtype == "UPLOAD":
        files = d.get("files")
        if not isinstance(files, list) or len(files) == 0:
            errors.append(f"{prefix}: UPLOAD 必须提供非空 files 数组")
        else:
            for fidx, f in enumerate(files):
                fp = f"{prefix} files[{fidx}]"
                if not isinstance(f, dict):
                    errors.append(f"{fp}: 必须是对象")
                    continue
                if "url" not in f:
                    errors.append(f"{fp}: 缺少 url")
                if "fileName" not in f:
                    errors.append(f"{fp}: 缺少 fileName")

    elif qtype == "GENERIC":
        if "value" not in d:
            errors.append(f"{prefix}: GENERIC 建议提供 value 字段")

    return errors


def _validate_option(prefix: str, opt: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(opt, dict):
        errors.append(f"{prefix}: option 必须是对象")
        return errors
    if "label" not in opt:
        errors.append(f"{prefix}: option 缺少 label")
    if "value" not in opt:
        errors.append(f"{prefix}: option 缺少 value")
    if opt.get("selected") is not True:
        errors.append(f"{prefix}: option selected 必须为 true")
    return errors


def _extract_questions_from_schema(schema: Dict[str, Any]) -> Dict[str, str]:
    """从 schema 提取所有题目的 uuid -> type 映射。"""
    mapping: Dict[str, str] = {}
    type_map = {
        "radioQuestions": "RADIO",
        "checkboxQuestions": "CHECKBOX",
        "textQuestions": "TEXTAREA",
        "uploadQuestions": "UPLOAD",
        "scaleQuestions": "SCALE",
        "matrixScaleQuestions": "MATRIX_SCALE",
        "genericQuestions": "GENERIC",
    }
    for key, qtype in type_map.items():
        for q in schema.get(key, []):
            uuid = q.get("uuid")
            if uuid:
                mapping[uuid] = qtype
    return mapping


def _validate_schema_structure(schema: Dict[str, Any]) -> List[str]:
    """校验 question_schema_generate.json 中每道题的字段完整性。

    防止 missing type / required 非 1/0 等导致 Java 端部分题目入库失败。
    """
    errors: List[str] = []
    type_map = {
        "radioQuestions": "RADIO",
        "checkboxQuestions": "CHECKBOX",
        "textQuestions": "TEXTAREA",
        "uploadQuestions": "UPLOAD",
        "scaleQuestions": "SCALE",
        "matrixScaleQuestions": "MATRIX_SCALE",
        "genericQuestions": "GENERIC",
    }
    # uuid 由 _auto_generate_schema_uuids 自动生成，不再要求 LLM 手写
    required_fields = ["title", "code", "type", "required", "sort"]

    for key, expected_type in type_map.items():
        questions = schema.get(key, [])
        if not isinstance(questions, list):
            continue
        for idx, q in enumerate(questions):
            if not isinstance(q, dict):
                errors.append(f"schema [{key}][{idx}]: 题目必须是对象")
                continue
            prefix = f"schema [{key}][{idx}] (code={q.get('code', 'N/A')})"

            # 必填字段检查
            for field in required_fields:
                if field not in q:
                    errors.append(f"{prefix}: 缺少必填字段 '{field}'")

            # type 检查
            qtype = q.get("type")
            if qtype is not None and qtype not in VALID_TYPES:
                errors.append(
                    f"{prefix}: type '{qtype}' 不合法，必须是 {', '.join(sorted(VALID_TYPES))} 之一"
                )
            if qtype is not None and qtype != expected_type:
                errors.append(
                    f"{prefix}: type '{qtype}' 与数组分类 '{key}' 不匹配（期望 '{expected_type}'）"
                )

            # required 检查
            req = q.get("required")
            if req is not None and req not in (0, 1):
                errors.append(f"{prefix}: required 必须是 0 或 1，当前值={req!r}")

            # sort 检查
            sort = q.get("sort")
            if sort is not None and (not isinstance(sort, int) or sort % 1000 != 0):
                errors.append(f"{prefix}: sort 必须是 1000 的整数倍，当前值={sort!r}")

            # id 字段禁止
            if "id" in q:
                errors.append(f"{prefix}: 禁止包含 'id' 字段")

            # 选项字段检查（RADIO / CHECKBOX）
            if expected_type in ("RADIO", "CHECKBOX"):
                opts = q.get("options")
                if not isinstance(opts, list) or len(opts) == 0:
                    errors.append(f"{prefix}: 必须提供非空 options 数组")
                else:
                    for oidx, opt in enumerate(opts):
                        if not isinstance(opt, dict):
                            errors.append(f"{prefix} options[{oidx}]: 必须是对象")
                            continue
                        if "label" not in opt:
                            errors.append(f"{prefix} options[{oidx}]: 缺少 label")
                        if "description" not in opt:
                            errors.append(f"{prefix} options[{oidx}]: 缺少 description（即使没有也要写 ''）")

            if expected_type == "CHECKBOX":
                min_raw = q.get("minChoices")
                max_raw = q.get("maxChoices")
                if min_raw is not None and (not isinstance(min_raw, int) or min_raw < 1):
                    errors.append(f"{prefix}: minChoices 必须 >= 1")
                if max_raw is not None and (not isinstance(max_raw, int) or max_raw < 1):
                    errors.append(f"{prefix}: maxChoices 必须 >= 1")
                if (
                    min_raw is not None
                    and max_raw is not None
                    and isinstance(min_raw, int)
                    and isinstance(max_raw, int)
                    and max_raw < min_raw
                ):
                    errors.append(f"{prefix}: maxChoices 必须 >= minChoices")

    return errors


def _cross_validate(answers: List[Dict], schema: Dict[str, Any]) -> List[str]:
    """交叉校验：检查 schema 中的每道题在 answers 中都有，且类型一致。"""
    errors: List[str] = []
    schema_questions = _extract_questions_from_schema(schema)
    answer_uuids = {}
    for idx, item in enumerate(answers):
        d = item.get("data", {})
        uuid = d.get("questionUuid")
        qtype = d.get("questionType")
        if uuid:
            answer_uuids[uuid] = qtype

    for uuid, expected_type in schema_questions.items():
        if uuid not in answer_uuids:
            errors.append(f"交叉校验: schema 中的题目 '{uuid}' 在 answers 中缺失")
        elif answer_uuids[uuid] != expected_type:
            errors.append(
                f"交叉校验: 题目 '{uuid}' 类型不一致，"
                f"schema 为 {expected_type}，answers 为 {answer_uuids[uuid]}"
            )

    for uuid in answer_uuids:
        if uuid not in schema_questions:
            errors.append(f"交叉校验: answers 中的题目 '{uuid}' 在 schema 中不存在")

    return errors


def _extract_question_uuids_from_script(all_script: str) -> Set[str]:
    """从问卷脚本（内联 HTML + 可选 survey-ui.js 合并源）提取 questionUuid。"""
    uuids: Set[str] = set()

    # 1) 字面量写法：questionUuid: "xxx"
    literal_matches = re.findall(r'["\']?questionUuid["\']?\s*:\s*["\']([^"\']+)["\']', all_script)
    for m in literal_matches:
        if m.strip():
            uuids.add(m.strip())

    # 2) 变量定义/引用写法：提取所有 32 位十六进制（如 const UUID_Q1 = 'a1b2...'）
    hex_matches = re.findall(r'\b[0-9a-f]{32}\b', all_script)
    for m in hex_matches:
        uuids.add(m)

    return uuids


def _extract_question_uuids_from_html_script(html_content: str, work_dir: Path | None = None) -> Set[str]:
    """从问卷脚本中提取所有 questionUuid 值（HTML 内联 + survey-ui.js 双轨）。"""
    all_script = _collect_free_mode_script_sources(html_content, work_dir)
    return _extract_question_uuids_from_script(all_script)


_DATA_QUESTION_UUID_ATTR_RE = re.compile(
    r'''data-question-uuid\s*=\s*["']([0-9a-f]{32})["']''',
    re.IGNORECASE,
)


def _extract_question_uuids_from_html_attrs(html_content: str) -> Set[str]:
    """从 HTML 全文的 data-question-uuid 属性提取 32 位 hex uuid。"""
    return set(_DATA_QUESTION_UUID_ATTR_RE.findall(html_content))


def _collect_located_html_uuids(html_content: str, work_dir: Path | None = None) -> Set[str]:
    """合并脚本字面量 uuid 与 HTML data-question-uuid 属性 uuid。"""
    script_values = _extract_question_uuids_from_html_script(html_content, work_dir)
    script_uuids = {v for v in script_values if _looks_like_uuid(v)}
    attr_uuids = _extract_question_uuids_from_html_attrs(html_content)
    return script_uuids | attr_uuids


def _format_missing_schema_uuid_message(
    missing_uuids: Set[str],
    code_uuid_map: Dict[str, Dict[str, str]],
) -> str:
    """schema uuid 在 HTML（脚本 + data-question-uuid）中未定位到时的报错文案。"""
    n = len(missing_uuids)
    codes = sorted(
        code for code, info in code_uuid_map.items() if info.get("uuid") in missing_uuids
    )
    code_hint = f"（涉及题目 code: {', '.join(codes)}）" if codes else ""
    return (
        f"schema 中有 {n} 道题的 uuid 在 HTML 中没有定位到{code_hint}，"
        f"请自行排查修复；若自行验证 uuid 一致，则忽略此提示。"
    )


def _format_extra_html_uuid_message(extra_uuids: Set[str]) -> str:
    n = len(extra_uuids)
    listed = ", ".join(sorted(extra_uuids))
    return (
        f"HTML 中定位到 {n} 个 schema 未定义的 uuid: {listed}。"
        f"请核对 data-question-uuid 与 question_schema_generate.json 是否一致。"
    )




def _extract_html_question_region(html_content: str, uuid: str) -> str | None:
    needle = f'data-question-uuid="{uuid}"'
    idx = html_content.find(needle)
    if idx < 0:
        return None
    start = html_content.rfind("<!-- QUESTION_REGION_START", 0, idx)
    if start < 0:
        start = html_content.rfind("<div data-question", 0, idx)
    if start < 0:
        start = idx
    end_markers = [
        html_content.find("<!-- QUESTION_REGION_END", idx),
        html_content.find("<div data-question", idx + len(needle)),
    ]
    end_candidates = [m for m in end_markers if m >= 0]
    end = min(end_candidates) if end_candidates else len(html_content)
    return html_content[start:end]


def _cross_validate_checkbox_html_attrs(html_content: str, schema: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for q in schema.get("checkboxQuestions", []) or []:
        uid = q.get("uuid") or ""
        code = q.get("code") or uid
        if not uid:
            continue
        region = _extract_html_question_region(html_content, uid)
        if region is None:
            errors.append(f"{code} (CHECKBOX) HTML 中找不到 data-question-uuid= {uid}")
            continue
        if "data-min-choices=" not in region:
            errors.append(f"{uid} (CHECKBOX) 缺少 data-min-choices")
        if "data-max-choices=" not in region:
            errors.append(f"{uid} (CHECKBOX) 缺少 data-max-choices")
        other_on = int(q.get("otherEnabled", 0) or 0) == 1
        opt_count = checkbox_option_count(q.get("options") or [], other_enabled=other_on)
        json_min, json_max = normalize_checkbox_choices(
            q.get("minChoices"), q.get("maxChoices"), option_count=opt_count
        )
        html_min_match = re.search(r'data-min-choices="(\d+)"', region)
        html_max_match = re.search(r'data-max-choices="(\d+)"', region)
        if html_min_match and int(html_min_match.group(1)) != json_min:
            errors.append(
                f"{uid} (CHECKBOX) data-min-choices 不一致: json={json_min}, html={html_min_match.group(1)}"
            )
        if html_max_match and int(html_max_match.group(1)) != json_max:
            errors.append(
                f"{uid} (CHECKBOX) data-max-choices 不一致: json={json_max}, html={html_max_match.group(1)}"
            )
    return errors


def _check_free_answer_validation_js(html_content: str, work_dir: Path | None) -> List[str]:
    merged = _collect_free_mode_script_sources(html_content, work_dir)
    if "FREE_ANSWER_VALIDATION" in merged and "WJFreeValidation" in merged:
        return []
    return [
        "survey-ui.js 缺少 FREE_ANSWER_VALIDATION / WJFreeValidation：请重新运行 generate_free_mode_skeleton.py 生成 survey-ui.js。"
    ]


def _cross_validate_html(html_content: str, schema: Dict[str, Any], work_dir: Path | None = None) -> List[str]:
    """交叉校验 HTML 中定位到的 uuid 与 schema 一致性（脚本字面量 + data-question-uuid 属性）。

    诊断逻辑：
    1. 脚本中若仍有 code 字面量作 questionUuid，单独提示
    2. schema uuid 与 HTML 定位 uuid 做集合差集
    """
    errors: List[str] = []
    html_values = _extract_question_uuids_from_html_script(html_content, work_dir)
    html_uuids = _collect_located_html_uuids(html_content, work_dir)
    code_uuid_map = _build_code_uuid_map(schema)
    schema_codes = set(code_uuid_map.keys())
    schema_uuids = {info["uuid"] for info in code_uuid_map.values() if info.get("uuid")}

    # 分类脚本中的值：code vs UUID（属性 uuid 不参与 code 检测）
    html_codes = {v for v in html_values if not _looks_like_uuid(v)}

    if html_codes:
        unknown_codes = html_codes - schema_codes
        if unknown_codes:
            errors.append(
                f"问卷脚本中使用了以下 code，但在 schema 中找不到对应题目: {', '.join(sorted(unknown_codes))}。"
                f"schema 中的 code 为: {', '.join(sorted(schema_codes))}。"
                f"请确保 JSON 的 'code' 字段与问卷脚本中的 questionUuid 值完全一致。"
            )
        known_codes = html_codes & schema_codes
        if known_codes:
            errors.append(
                f"问卷脚本中以下 code 未使用 UUID: {', '.join(sorted(known_codes))}。"
                f"请使用 schema 中的 uuid 值作为 questionUuid 和 state.answers 键。"
            )

    missing_in_html = schema_uuids - html_uuids
    extra_in_html = html_uuids - schema_uuids

    if missing_in_html:
        errors.append(_format_missing_schema_uuid_message(missing_in_html, code_uuid_map))

    if extra_in_html:
        errors.append(_format_extra_html_uuid_message(extra_in_html))

    return errors


def _collect_free_mode_script_sources(html_content: str, work_dir: Path | None) -> str:
    """合并 HTML 内联 script 与 survey-ui.js（若存在且非占位）。"""
    inline_scripts = re.findall(
        r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
        html_content,
        re.DOTALL | re.IGNORECASE,
    )
    parts = ["\n".join(inline_scripts)]
    if work_dir is not None:
        js_path = work_dir / "survey-ui.js"
        if js_path.is_file():
            js_content = js_path.read_text(encoding="utf-8")
            if not any(marker in js_content for marker in _JS_PLACEHOLDER_MARKERS):
                parts.append(js_content)
    return "\n".join(parts)


_SUBMIT_CHAIN_WARNING_SUFFIX = (
    "若用户需求为「收集答案后不提交统计、仅展示测评结果」，可忽略；"
    "否则请补全 submitSurvey() → SurveyDataBridge.submit(buildAnswers(), …) 提交链路。"
)


def _check_html_submit(html_content: str, work_dir: Path | None = None) -> List[str]:
    """检查问卷脚本中是否包含规范的提交调用（仅警告，不阻断校验）。"""
    warnings: List[str] = []
    all_script_content = _collect_free_mode_script_sources(html_content, work_dir)

    if "SurveyDataBridge" not in all_script_content:
        warnings.append(
            f"问卷脚本中未找到 SurveyDataBridge 引用。{_SUBMIT_CHAIN_WARNING_SUFFIX}"
        )
        return warnings

    if "SurveyDataBridge.submit" not in all_script_content:
        warnings.append(
            f"问卷脚本中未找到 SurveyDataBridge.submit() 调用。{_SUBMIT_CHAIN_WARNING_SUFFIX}"
        )
        return warnings

    # 简单启发式：检查是否传入了看起来是数组的参数
    submit_calls = re.findall(
        r"SurveyDataBridge\.submit\s*\(([^)]*)\)", all_script_content, re.DOTALL
    )
    if not submit_calls:
        warnings.append(
            f"无法解析 SurveyDataBridge.submit 的调用参数。{_SUBMIT_CHAIN_WARNING_SUFFIX}"
        )
    else:
        for call in submit_calls:
            call_str = call.strip()
            if not call_str:
                warnings.append(
                    f"SurveyDataBridge.submit() 被无参调用，建议传入 answers 和 originSurveyAnswer。"
                    f"{_SUBMIT_CHAIN_WARNING_SUFFIX}"
                )
            elif (
                "document.documentElement.outerHTML" not in all_script_content
                and "originSurveyAnswer" not in call_str
            ):
                warnings.append(
                    "SurveyDataBridge.submit() 调用中似乎未包含 originSurveyAnswer（页面 HTML 快照）。"
                    f"{_SUBMIT_CHAIN_WARNING_SUFFIX}"
                )

    return warnings


def _collect_free_mode_css_sources(html_content: str, work_dir: Path | None) -> str:
    """合并 head 内联 LLM CSS 区与 survey-ui.css（若存在且非占位）。"""
    parts: List[str] = []
    head = _extract_head_html(html_content)
    if _CSS_REGION_BEGIN in head:
        parts.append(head)
    if work_dir is not None:
        css_path = work_dir / "survey-ui.css"
        if css_path.is_file():
            css_content = css_path.read_text(encoding="utf-8")
            if not any(marker in css_content for marker in _CSS_PLACEHOLDER_MARKERS):
                parts.append(css_content)
    return "\n".join(parts)


def _css_has_absolute_stacked_questions(css: str) -> bool:
    """[data-question] 规则块内同时含 position:absolute 与 top:0（叠卡分页反模式）。"""
    css_stripped = _strip_css_comments(css)
    for match in re.finditer(r"\[data-question\][^{]*\{([^}]*)\}", css_stripped, re.IGNORECASE | re.DOTALL):
        body = match.group(1)
        if re.search(r"position\s*:\s*absolute\b", body, re.IGNORECASE) and re.search(
            r"top\s*:\s*0\b", body, re.IGNORECASE
        ):
            return True
    return False


def _css_has_fixed_bottom_nav(css: str) -> bool:
    """任一规则块内同时含 position:fixed 与 bottom（安全底栏导航）。"""
    css_stripped = _strip_css_comments(css)
    for match in re.finditer(r"\{([^}]*)\}", css_stripped, re.DOTALL):
        body = match.group(1)
        if re.search(r"position\s*:\s*fixed\b", body, re.IGNORECASE) and re.search(
            r"bottom\s*:", body, re.IGNORECASE
        ):
            return True
    return False


def _has_immersive_nav_intent(html_content: str, work_dir: Path | None) -> bool:
    """JS/HTML 中是否存在沉浸式「下一题」导航意图。"""
    js = _collect_free_mode_script_sources(html_content, work_dir)
    merged = f"{js}\n{html_content}"
    patterns = (
        r"下一题",
        r"""data-nav\s*=\s*["']next["']""",
        r"survey-nav",
        r"data-nav-action",
    )
    return any(re.search(p, merged) for p in patterns)


_IMMERSIVE_NAV_LAYOUT_WARNING = (
    "沉浸式布局风险：[data-question] 使用 position:absolute; top:0，且存在「下一题」导航，"
    "但未见 position:fixed 底栏（含 bottom）。导航若插在题前兄弟节点易被题卡遮挡。"
    "请改为 display:none/.active + fixed 底栏，或把导航挂进题卡内（见 F1 沉浸式分页契约第 5 条）。"
)


def _check_immersive_nav_layout(html_content: str, work_dir: Path | None = None) -> List[str]:
    """absolute 叠卡 + 兄弟导航且无 fixed 底栏 → warning（不阻断）。"""
    if not _has_immersive_nav_intent(html_content, work_dir):
        return []
    css = _collect_free_mode_css_sources(html_content, work_dir)
    if not css or not _css_has_absolute_stacked_questions(css):
        return []
    if _css_has_fixed_bottom_nav(css):
        return []
    return [_IMMERSIVE_NAV_LAYOUT_WARNING]


# ----- hide-all 首屏闭环（静态启发式，warning 不阻断） -----

_QUESTION_RULE_SELECTOR = (
    r"(?:\[data-survey-role\s*=\s*['\"]survey['\"]\]\s*)?\[data-question\]"
)

_HIDE_ALL_FIRST_PAINT_WARNING = (
    "白屏风险：[data-question] 默认 display:none，但无法证明首屏会显示"
    "（无静态 .active / 无 showPage(n>=1) / showPage(0) 缺欢迎壳 / 无启动加 .active / 无套件 intro 启动显示）。"
    "请补欢迎页与导航 DOM，或初始 showPage(1)，或保证启动逻辑给当前题加 .active。"
)


def _iter_question_css_rule_bodies(css: str) -> List[str]:
    """提取与 [data-question] 相关的 CSS 规则块 body。"""
    css_stripped = _strip_css_comments(css)
    pattern = _QUESTION_RULE_SELECTOR + r"(?:\.[a-zA-Z0-9_-]+|\[[^\]]+\])?[^{]*\{([^}]*)\}"
    return [m.group(1) for m in re.finditer(pattern, css_stripped, re.IGNORECASE | re.DOTALL)]


def _css_has_question_scroll_override(css: str) -> bool:
    """滚动兜底：同选择器族对 [data-question] 强制 block/flex !important。"""
    css_stripped = _strip_css_comments(css)
    pattern = (
        _QUESTION_RULE_SELECTOR
        + r"(?:\.[a-zA-Z0-9_-]+|\[[^\]]+\])?[^{]*\{([^}]*)\}"
    )
    for match in re.finditer(pattern, css_stripped, re.IGNORECASE | re.DOTALL):
        body = match.group(1)
        selector_text = match.group(0).split("{", 1)[0]
        if ".active" in selector_text:
            continue
        if re.search(
            r"display\s*:\s*(?:block|flex)\s*!important\b", body, re.IGNORECASE
        ):
            return True
    return False


def _css_hides_all_questions(css: str) -> bool:
    """基础 [data-question] 规则是否 display:none（沉浸式分页常见形态）。"""
    if not css or not css.strip():
        return False
    if _css_has_question_scroll_override(css):
        return False
    css_stripped = _strip_css_comments(css)
    base_hide = False
    active_reveal = False
    base_pattern = _QUESTION_RULE_SELECTOR + r"(?![.\[])[^{]*\{([^}]*)\}"
    active_pattern = _QUESTION_RULE_SELECTOR + r"\.active[^{]*\{([^}]*)\}"
    for match in re.finditer(base_pattern, css_stripped, re.IGNORECASE | re.DOTALL):
        body = match.group(1)
        if re.search(r"display\s*:\s*none\b", body, re.IGNORECASE):
            base_hide = True
            break
    for match in re.finditer(active_pattern, css_stripped, re.IGNORECASE | re.DOTALL):
        body = match.group(1)
        if re.search(r"display\s*:\s*(?:block|flex)\b", body, re.IGNORECASE):
            active_reveal = True
            break
    if base_hide:
        return True
    # 仅有 display:none 且无 .active 配对时仍视为 hide-all
    for body in _iter_question_css_rule_bodies(css):
        if re.search(r"display\s*:\s*none\b", body, re.IGNORECASE):
            if not active_reveal:
                return True
    return False


def _html_has_welcome_shell(html: str) -> bool:
    """是否存在欢迎页壳（不要求 active）。"""
    if re.search(r"""id\s*=\s*["']welcomeScreen["']""", html, re.IGNORECASE):
        return True
    if re.search(r"""class\s*=\s*["'][^"']*\bwelcome-screen\b[^"']*["']""", html, re.IGNORECASE):
        return True
    return False


def _html_has_static_visible_surface(html: str) -> bool:
    """静态 HTML 是否已有首屏可见面（题或 welcome 带 active）。"""
    if re.search(
        r"""<div\b[^>]*\bdata-question\b[^>]*\bclass\s*=\s*["'][^"']*\bactive\b[^"']*["']""",
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        return True
    if re.search(
        r"""id\s*=\s*["']welcomeScreen["'][^>]*\bclass\s*=\s*["'][^"']*\bactive\b""",
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        return True
    if re.search(
        r"""class\s*=\s*["'][^"']*\bwelcome-screen\b[^"']*\bactive\b[^"']*["']""",
        html,
        re.IGNORECASE,
    ):
        return True
    return False


def _js_initial_show_page(js: str) -> int | None:
    """从启动路径抽取 showPage(N) 的字面量页码。"""
    stripped = _strip_js_comments(js)
    boot_patterns = (
        r"DOMContentLoaded[\s\S]{0,400}?showPage\s*\(\s*(\d+)\s*\)",
        r"readyState[\s\S]{0,120}?else[\s\S]{0,120}?showPage\s*\(\s*(\d+)\s*\)",
        r"bindNav\s*\(\s*\)\s*;\s*showPage\s*\(\s*(\d+)\s*\)",
    )
    for pattern in boot_patterns:
        match = re.search(pattern, stripped, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _js_boots_question_active(js: str) -> bool:
    """启动路径是否会给题卡加 .active（覆盖 showQ / exam 的 showQ=function；不含 showPage 内部逻辑）。"""
    stripped = _strip_js_comments(js)
    # assessment: function showQ(...)；exam step: showQ = function (...)
    has_show_q_impl = bool(
        re.search(
            r"(?:function\s+showQ\s*\([^)]*\)|showQ\s*=\s*function\s*\([^)]*\))"
            r"\s*\{[\s\S]{0,400}?classList\.(?:toggle|add)\s*\(\s*['\"]active['\"]",
            stripped,
            re.IGNORECASE,
        )
    )
    boot_show_q = bool(
        re.search(
            r"(?:DOMContentLoaded|readyState[\s\S]{0,120}?else|wireIntro|startExam|function\s+start\s*\()"
            r"[\s\S]{0,500}?showQ\s*\(\s*\d+\s*\)",
            stripped,
            re.IGNORECASE,
        )
    )
    if has_show_q_impl and boot_show_q:
        return True
    return bool(
        re.search(
            r"DOMContentLoaded[\s\S]{0,500}?questions[\s\S]{0,150}?classList\.toggle\s*\(\s*['\"]active['\"]\s*,",
            stripped,
            re.IGNORECASE,
        )
    )


def _js_boots_suite_intro(html: str, js: str) -> bool:
    """exam/assessment intro 壳存在且 JS 启动会将其 display 设为 flex/block。"""
    has_exam = re.search(r"""id\s*=\s*["']exam-intro["']""", html, re.IGNORECASE)
    has_eval = re.search(r"""id\s*=\s*["']eval-intro["']""", html, re.IGNORECASE)
    if not has_exam and not has_eval:
        return False
    stripped = _strip_js_comments(js)
    intro_display_patterns = (
        r"exam-intro[\s\S]{0,120}?\.style\.display\s*=\s*['\"](?:flex|block)['\"]",
        r"eval-intro[\s\S]{0,120}?\.style\.display\s*=\s*['\"](?:flex|block)['\"]",
        r"byId\s*\(\s*['\"]exam-intro['\"]\s*\)[\s\S]{0,120}?\.style\.display\s*=\s*['\"](?:flex|block)['\"]",
        r"byId\s*\(\s*['\"]eval-intro['\"]\s*\)[\s\S]{0,120}?\.style\.display\s*=\s*['\"](?:flex|block)['\"]",
        r"intro\.style\.display\s*=\s*['\"](?:flex|block)['\"]",
    )
    return any(re.search(p, stripped, re.IGNORECASE) for p in intro_display_patterns)


def _check_hide_all_first_paint(
    html_content: str, work_dir: Path | None = None
) -> List[str]:
    """hide-all 且无法证明首屏 → warning 列表（0 或 1 条）。"""
    css = _collect_free_mode_css_sources(html_content, work_dir)
    if not _css_hides_all_questions(css):
        return []

    js = _collect_free_mode_script_sources(html_content, work_dir)

    if _html_has_static_visible_surface(html_content):
        return []
    if _css_has_question_scroll_override(css):
        return []

    boot_page = _js_initial_show_page(js)
    if boot_page is not None and boot_page >= 1:
        return []
    if boot_page == 0 and _html_has_welcome_shell(html_content):
        return []
    if _js_boots_question_active(js):
        return []
    if _js_boots_suite_intro(html_content, js):
        return []

    return [_HIDE_ALL_FIRST_PAINT_WARNING]


def _has_dynamic_answer_writes(all_script: str) -> bool:
    """是否通过变量键写入 state.answers（如翻页模板 state.answers[uuid]）。"""
    patterns = (
        r"state\.answers\s*\[\s*uuid\s*\]\s*=",
        r"state\.answers\s*\[\s*q\.dataset\.questionUuid\s*\]\s*=",
    )
    return any(re.search(p, all_script) for p in patterns)


def _extract_build_answers_literal_keys(all_script: str) -> Set[str]:
    """从 buildAnswers 函数体提取 state.answers 字面量键。"""
    m = re.search(r"function\s+buildAnswers\s*\(\s*\)\s*\{", all_script)
    if not m:
        return set()
    rest = all_script[m.start() : m.start() + 8000]
    return set(re.findall(r"state\.answers\s*\[\s*['\"]([^'\"]+)['\"]\s*\]", rest))


def _check_answer_key_consistency(html_content: str, work_dir: Path | None = None) -> List[str]:
    """检查 state.answers 的赋值键名和读取键名是否一致（不依赖函数名）。"""
    errors: List[str] = []

    all_script = _collect_free_mode_script_sources(html_content, work_dir)

    # 未使用 state.answers 则跳过（可能是直接内联构造 answers）
    if "state.answers" not in all_script:
        return errors

    dynamic_writes = _has_dynamic_answer_writes(all_script)

    # 提取赋值键名：state.answers['xxx'] = ...
    write_keys = set(re.findall(r"state\.answers\s*\[\s*['\"]([^'\"]+)['\"]\s*\]\s*=?=", all_script))

    # 仅变量键写入（如 state.answers[uuid]）且 buildAnswers 用字面量 UUID 读取 —— 允许
    if not write_keys:
        if dynamic_writes:
            return errors
        return errors

    # 提取所有读取键名（包含赋值场景），再减去赋值键
    all_keys = set(re.findall(r"state\.answers\s*\[\s*['\"]([^'\"]+)['\"]\s*\]", all_script))
    read_keys = all_keys - write_keys

    only_reads = read_keys - write_keys
    if dynamic_writes and only_reads:
        build_keys = _extract_build_answers_literal_keys(all_script)
        only_reads = only_reads - build_keys

    if only_reads:
        errors.append(
            f"读取了未赋值的 state.answers 键: {', '.join(sorted(only_reads))}。"
            f"存取键名必须一致（推荐统一使用 UUID 作为键）。"
        )

    return errors


_CSS_REGION_BEGIN = "LLM 自定义 CSS 区域 BEGIN"
_CSS_REGION_END = "LLM 自定义 CSS 区域 END"
_CSS_PLACEHOLDER_MARKERS = ("自由模式 CSS 占位",)
_CSS_MISSING_MESSAGE = (
    "卷面缺少可渲染的自定义样式：请在 survey-ui.css 的 LLM 自定义 CSS 区补充各题型样式"
)
_CSS_FILE_MISSING_MESSAGE = (
    "survey-ui.css 不存在。HTML 已外链 ./survey-ui.css，入库与渲染需要该文件。"
    "请在当前工作目录补写自由模式样式骨架（含「LLM 自定义 CSS 区域 BEGIN/END」），"
)


def _check_survey_ui_css_file_exists(html: str, work_dir: Path | None) -> List[str]:
    """HTML 外链 survey-ui.css 时要求文件存在（存在性兜底；实质样式仍由 _check_css_structure 检查）。"""
    if work_dir is None:
        return []
    if not re.search(r"survey-ui\.css", html, re.IGNORECASE):
        return []
    css_path = work_dir / "survey-ui.css"
    if css_path.is_file():
        return []
    return [f"{_CSS_FILE_MISSING_MESSAGE} 期望路径: {css_path}"]

_JS_REGION_BEGIN = "LLM 自定义交互逻辑区域 BEGIN"
_JS_REGION_END = "LLM 自定义交互逻辑区域 END"
_JS_PLACEHOLDER_MARKERS = ("自由模式 JS 占位",)
_JS_MISSING_MESSAGE = "卷面缺少可运行的交互逻辑：请在 survey-ui.js 补充交互逻辑"


def _strip_css_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL).strip()


def _extract_llm_css_region(text: str) -> str:
    begin_idx = text.find(_CSS_REGION_BEGIN)
    end_idx = text.find(_CSS_REGION_END)
    if begin_idx == -1 or end_idx == -1 or end_idx <= begin_idx:
        return ""
    return text[begin_idx + len(_CSS_REGION_BEGIN) : end_idx]


def _has_actual_css_in_llm_region(text: str) -> bool:
    region = _extract_llm_css_region(text)
    if not region:
        return False
    return bool(_strip_css_comments(region))


def _extract_head_html(html: str) -> str:
    match = re.search(r"<head\b[^>]*>(.*?)</head>", html, re.IGNORECASE | re.DOTALL)
    return match.group(1) if match else ""


def _has_head_inline_llm_css(html: str) -> bool:
    """仅检查 head 内联 LLM CSS 区（不含 GENERIC 题 per-question style）。"""
    head = _extract_head_html(html)
    if _CSS_REGION_BEGIN not in head:
        return False
    return _has_actual_css_in_llm_region(head)


def _has_survey_ui_css_file(work_dir: Path | None) -> bool:
    if work_dir is None:
        return False
    css_path = work_dir / "survey-ui.css"
    if not css_path.is_file():
        return False
    css_content = css_path.read_text(encoding="utf-8")
    if any(marker in css_content for marker in _CSS_PLACEHOLDER_MARKERS):
        return False
    return _has_actual_css_in_llm_region(css_content)


def _check_css_structure(html: str, work_dir: Path | None) -> List[str]:
    """CSS 校验：head 内联 LLM 区或 survey-ui.css 任一有实际样式即通过。"""
    if _has_head_inline_llm_css(html) or _has_survey_ui_css_file(work_dir):
        return []
    return [_CSS_MISSING_MESSAGE]


def _strip_js_comments(js: str) -> str:
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.DOTALL)
    js = re.sub(r"//[^\n]*", "", js)
    return js.strip()


def _extract_llm_js_region(text: str) -> str:
    begin_idx = text.find(_JS_REGION_BEGIN)
    end_idx = text.find(_JS_REGION_END)
    if begin_idx == -1 or end_idx == -1 or end_idx <= begin_idx:
        return ""
    return text[begin_idx + len(_JS_REGION_BEGIN) : end_idx]


def _has_actual_js_in_llm_region(text: str) -> bool:
    region = _extract_llm_js_region(text)
    if not region:
        return False
    stripped = _strip_js_comments(region)
    return bool(stripped)


def _has_body_inline_llm_js(html: str) -> bool:
    """检查 body 或全文档内联 script 是否含 LLM JS 区且有实质逻辑。"""
    body_match = re.search(r"<body\b[^>]*>(.*?)</body>", html, re.IGNORECASE | re.DOTALL)
    body = body_match.group(1) if body_match else html
    if _JS_REGION_BEGIN not in body and _JS_REGION_BEGIN not in html:
        return False
    target = body if _JS_REGION_BEGIN in body else html
    return _has_actual_js_in_llm_region(target)


def _has_survey_ui_js_file(work_dir: Path | None) -> bool:
    if work_dir is None:
        return False
    js_path = work_dir / "survey-ui.js"
    if not js_path.is_file():
        return False
    js_content = js_path.read_text(encoding="utf-8")
    if any(marker in js_content for marker in _JS_PLACEHOLDER_MARKERS):
        return False
    if _has_actual_js_in_llm_region(js_content):
        return True
    if "function buildAnswers()" in js_content and "SurveyDataBridge.submit" in js_content:
        return True
    return False


def _check_js_structure(html: str, work_dir: Path | None) -> List[str]:
    """JS 校验：内联 LLM 区或 survey-ui.js 任一侧有实质逻辑，或合并源含 buildAnswers+submit 即通过。"""
    if _has_body_inline_llm_js(html) or _has_survey_ui_js_file(work_dir):
        return []
    merged = _collect_free_mode_script_sources(html, work_dir)
    if "function buildAnswers()" in merged and "SurveyDataBridge.submit" in merged:
        return []
    return [_JS_MISSING_MESSAGE]


def _check_survey_ui_js_syntax(work_dir: Path | None) -> List[str]:
    """对 survey-ui.js 做 node --check（与标准模式 validate_standard_survey 对齐）。

    无文件、占位内容则跳过；SyntaxError 记为 error。
    node 未安装：跳过检查并 print 引导 Agent 自行复核 JS 语法（不记 error、不阻断）。
    """
    if work_dir is None:
        return []
    js_path = work_dir / "survey-ui.js"
    if not js_path.is_file():
        return []
    content = js_path.read_text(encoding="utf-8")
    if not content.strip():
        return []
    if any(marker in content for marker in _JS_PLACEHOLDER_MARKERS):
        return []
    errors, _node_skipped = check_js_file(
        js_path,
        skip_message=(
            "[SKIP] node 未安装，已跳过 survey-ui.js 的 node --check。"
            "请自行复核 JS 语法（注释边界完整、无裸露中文/残缺 /* */、括号与 IIFE 配对）；"
            f"有 node 时优先: node --check {js_path}"
        ),
    )
    return errors


def _check_render_guard(html_content: str) -> List[str]:
    """只校验**结构性必需**项：标准根容器 [data-survey-role="survey"]（基座/桥/守卫都靠它定位题目，缺了卷子跑不起来）。
    白屏守卫(RENDER_GUARD)是默认注入的兜底安全网，属"建议保留"而非硬性要求——LLM 有特殊显隐方案时可调整/移除，
    这里**不**强制它存在（脚手架是帮你少踩坑，不是限制你）。"""
    errors: List[str] = []
    if 'data-survey-role="survey"' not in html_content:
        errors.append(
            "缺少根容器 [data-survey-role=\"survey\"]：题目必须包裹在该根容器内（基座/桥定位题目都依赖它）。"
        )
    return errors


def run_html_checks(
    html_path: Path,
    schema: Dict[str, Any] | None = None,
    work_dir: Path | None = None,
) -> Tuple[List[str], List[str]]:
    """HTML 内联脚本与可选 schema 的单路径校验（避免 main 重复调用）。

    返回 (errors, warnings)；提交链路问题仅记入 warnings，不阻断校验。
    """
    errors: List[str] = []
    warnings: List[str] = []
    if not html_path.exists():
        errors.append(f"HTML 文件不存在: {html_path}")
        return errors, warnings

    html_content = html_path.read_text(encoding="utf-8")
    resolved_work_dir = work_dir if work_dir is not None else html_path.parent
    errors.extend(_check_survey_ui_css_file_exists(html_content, resolved_work_dir))
    errors.extend(_check_css_structure(html_content, resolved_work_dir))
    errors.extend(_check_js_structure(html_content, resolved_work_dir))
    errors.extend(_check_survey_ui_js_syntax(resolved_work_dir))
    warnings.extend(_check_html_submit(html_content, resolved_work_dir))
    warnings.extend(_check_immersive_nav_layout(html_content, resolved_work_dir))
    warnings.extend(_check_hide_all_first_paint(html_content, resolved_work_dir))
    errors.extend(_check_answer_key_consistency(html_content, resolved_work_dir))
    errors.extend(_check_render_guard(html_content))
    errors.extend(_check_free_answer_validation_js(html_content, resolved_work_dir))

    if schema is not None:
        errors.extend(_validate_schema_structure(schema))
        errors.extend(validate_schema_generic_chart_html(schema))

        html_values = _extract_question_uuids_from_html_script(html_content, resolved_work_dir)
        remaining_codes = {v for v in html_values if not _looks_like_uuid(v)}
        if remaining_codes:
            errors.append(
                f"HTML 中仍有以下 code 字面量未使用 UUID: {', '.join(sorted(remaining_codes))}。"
                f"请确保 questionUuid 和 state.answers 键均使用 schema 中的 uuid 值。"
            )

        errors.extend(_cross_validate_html(html_content, schema, resolved_work_dir))
        errors.extend(_cross_validate_checkbox_html_attrs(html_content, schema))

    return errors, warnings


def _dedupe_messages(messages: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for msg in messages:
        if msg not in seen:
            seen.add(msg)
            out.append(msg)
    return out


def _extract_uuids_from_schema(schema: Dict[str, Any]) -> Set[str]:
    """从 schema 中提取所有题目的 uuid。"""
    uuids: Set[str] = set()
    for key in QUESTION_ARRAY_KEYS:
        for q in schema.get(key, []):
            u = q.get("uuid")
            if isinstance(u, str) and u:
                uuids.add(u)
    return uuids


def _is_java_compatible_uuid(u: str) -> bool:
    """Java 兼容 UUID：32 位无连字符十六进制，且符合 UUID v4 规范。

    Java 的 UUID.fromString() 会校验版本位和变体位：
    - 版本位（index 12）必须是 4
    - 变体位（index 16）必须是 8/9/a/b（二进制 10xx）
    """
    if not re.fullmatch(r"[0-9a-f]{32}", u):
        return False
    return u[12] == "4" and u[16] in "89ab"


def _looks_like_uuid(s: str) -> bool:
    """判断字符串是否已经是 32 位 hex UUID 格式（不校验版本位）。"""
    return bool(re.fullmatch(r"[0-9a-f]{32}", s))


def _build_code_uuid_map(schema: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """从 schema 建立 code -> {uuid, type, title} 映射。"""
    mapping: Dict[str, Dict[str, str]] = {}
    for key in QUESTION_ARRAY_KEYS:
        for q in schema.get(key, []):
            code = q.get("code")
            if code:
                mapping[code] = {
                    "uuid": q.get("uuid", ""),
                    "type": q.get("type", ""),
                    "title": q.get("title", ""),
                }
    return mapping


def _extract_schema_questions(schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 schema 提取所有题目对象列表（平铺）。"""
    out: List[Dict[str, Any]] = []
    for key in QUESTION_ARRAY_KEYS:
        out.extend(schema.get(key, []))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="自由模式提交数据校验器")
    parser.add_argument("--json", help="answers JSON 文件路径")
    parser.add_argument("--schema", help="question_schema_generate.json 路径（用于交叉校验）")
    parser.add_argument("--html", help="survey-unified-generate.html 路径（检查问卷脚本中的提交调用）")
    parser.add_argument(
        "--dir",
        default=None,
        help="产物工作目录；校验通过后将删除该目录下 *spec.json 草稿（默认从 --schema/--html 推断）",
    )
    parser.add_argument(
        "--keep-spec",
        action="store_true",
        help="校验通过后保留 spec 草稿（调试用）",
    )
    args = parser.parse_args()

    all_errors: List[str] = []
    all_warnings: List[str] = []
    loaded_schema: Dict[str, Any] | None = None

    if args.schema:
        schema_path = Path(args.schema)
        if schema_path.exists():
            try:
                loaded_schema = json.loads(schema_path.read_text(encoding="utf-8"))
            except Exception as e:
                all_errors.append(f"Schema 解析失败: {e}")
        else:
            all_errors.append(f"Schema 文件不存在: {schema_path}")

    work_dir: Path | None = Path(args.dir).resolve() if args.dir else None

    if args.html:
        html_path = Path(args.html)
        try:
            html_errors, html_warnings = run_html_checks(
                html_path, loaded_schema, work_dir=work_dir
            )
            all_errors.extend(html_errors)
            all_warnings.extend(html_warnings)
        except Exception as e:
            all_errors.append(f"HTML 校验失败: {e}")

    # 校验 answers JSON
    if args.json:
        json_path = Path(args.json)
        if not json_path.exists():
            all_errors.append(f"JSON 文件不存在: {json_path}")
        else:
            try:
                with json_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                all_errors.extend(validate_answers(data))

                # schema 结构校验 + 交叉校验
                if args.schema:
                    schema_path = Path(args.schema)
                    if schema_path.exists():
                        with schema_path.open("r", encoding="utf-8") as f:
                            schema = json.load(f)
                        all_errors.extend(_validate_schema_structure(schema))
                        all_errors.extend(_cross_validate(data, schema))
                    else:
                        all_errors.append(f"Schema 文件不存在: {schema_path}")
            except json.JSONDecodeError as e:
                all_errors.append(f"JSON 解析失败: {e}")

    all_errors = _dedupe_messages(all_errors)
    all_warnings = _dedupe_messages(all_warnings)

    if all_errors:
        print(f"❌ 校验失败，发现 {len(all_errors)} 处错误:")
        for err in all_errors:
            print(f"  - {err}")
        if all_warnings:
            print(f"\n⚠ 另有 {len(all_warnings)} 处警告（不阻断校验）:")
            for warn in all_warnings:
                print(f"  - {warn}")
        return 1

    print("✅ 校验通过")
    if all_warnings:
        print(f"⚠ 发现 {len(all_warnings)} 处警告（不阻断校验）:")
        for warn in all_warnings:
            print(f"  - {warn}")

    if not args.keep_spec:
        work_dir: Path | None = None
        if args.dir:
            work_dir = Path(args.dir).resolve()
        else:
            for candidate in (
                Path(args.schema) if args.schema else None,
                Path(args.html) if args.html else None,
            ):
                if candidate is not None and candidate.exists():
                    work_dir = candidate.resolve().parent
                    break
        if work_dir is not None:
            removed: list[Path] = []
            for path in sorted(work_dir.glob("*spec.json")):
                if path.is_file():
                    path.unlink()
                    removed.append(path.resolve())
            if removed:
                print(f"已清理 spec 草稿 ({len(removed)} 个):")
                for p in removed:
                    print(f"  - {p}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
