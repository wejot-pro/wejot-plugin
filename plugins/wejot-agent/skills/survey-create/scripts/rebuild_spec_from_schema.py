#!/usr/bin/env python3
"""从 question_schema_generate.json 与 survey-unified-generate.html 逆映射题目信息为 survey_spec.json。

说明：
- 输入为按题型分桶的 question_schema 格式（工作目录下 question_schema_generate.json）。
- 输出为统一 questions 数组的 survey_spec 格式，供 generate_standard_survey.py 再次生成使用。
- 题目 description：仅从各题型 bucket 中题目对象的 `description` 字段读取并写回 spec。
- HTML 仅用于：各题 data-page → spec.page；GENERIC 题的 style/html/script 片段（schema 不存的部分）。
- schema 不含的字段会回填默认值（见 IRREVERSIBLE_DEFAULTS）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_standard_survey import (  # noqa: E402
    ALLOWED_FILE_EXTENSIONS,
    MAX_UPLOAD_FILE_COUNT,
    MAX_UPLOAD_FILE_SIZE_KB,
    normalize_file_types,
)
from survey_ui_i18n import (  # noqa: E402
    html_dict_for_locale,
    load_locale_dict_file,
    other_labels_for_locale,
    warn_if_custom_locale_needed,
)
from utils.checkbox_choices import checkbox_option_count, normalize_checkbox_choices  # noqa: E402

OUTPUT_SPEC_NAME = "survey_spec.json"

# 这些字段不在 question_schema_generate.json 中，只能从HTML恢复。
IRREVERSIBLE_DEFAULTS: dict[str, Any] = {
    "page": 1,
    "genericStyle": "/* custom question style content */",
    "genericHtml": "<!-- custom question html structure -->",
    "genericScript": "/* ========== custom question submit script (AI writes here) ========== */",
}

TYPE_BUCKETS: list[tuple[str, str]] = [
    ("RADIO", "radioQuestions"),
    ("CHECKBOX", "checkboxQuestions"),
    ("TEXTAREA", "textQuestions"),
    ("UPLOAD", "uploadQuestions"),
    ("SCALE", "scaleQuestions"),
    ("MATRIX_SCALE", "matrixScaleQuestions"),
    ("GENERIC", "genericQuestions"),
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _to_required_bool(v: Any) -> bool:
    """将 schema 中的 required 字段转换为 bool 类型。"""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v != 0
    if isinstance(v, str):
        normalized = v.strip().lower()
        if normalized in {"", "0", "false", "no", "none", "null"}:
            return False
        if normalized in {"1", "true", "yes"}:
            return True
        return True
    return bool(v)


def _question_description_from_schema(raw: dict[str, Any]) -> str:
    """题目说明：只认 question_schema_generate.json 中的 description，不从 HTML 取。"""
    v = raw.get("description", "")
    if v is None:
        return ""
    return str(v)


def _base_question(raw: dict[str, Any], qtype: str) -> dict[str, Any]:
    # 与 minimal_survey_spec.json 中题目公共字段顺序一致；description 仅来自 schema
    return {
        "title": raw.get("title", ""),
        "type": qtype,
        "required": _to_required_bool(raw.get("required", 0)),
        "page": IRREVERSIBLE_DEFAULTS["page"],
        "code": raw.get("code", ""),
        "description": _question_description_from_schema(raw),
        "_sort": int(raw.get("sort", 0)),
    }


def _normalize_option_labels(options: Any) -> list[str]:
    if not isinstance(options, list):
        return []
    out: list[str] = []
    for item in sorted(options, key=lambda x: int((x or {}).get("sort", 0))):
        if isinstance(item, dict):
            out.append(str(item.get("label", "")))
    return out


def _normalize_scale_like(options: Any) -> list[dict[str, Any]]:
    if not isinstance(options, list):
        return []
    out: list[dict[str, Any]] = []
    for item in sorted(options, key=lambda x: int((x or {}).get("sort", 0))):
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "sort": int(item.get("sort", 0)),
                "score": float(item.get("score", 0)),
                "title": str(item.get("title", "")),
            }
        )
    return out


def _extract_generic_script_body(script_text: str) -> str:
    # 优先匹配 generate 模板中外层 try/catch（避免 isValidUrl 等内层 try 截断 AI 脚本）
    outer = re.search(
        r"try\s*\{([\s\S]*)\}\s*catch\s*\(\s*e\s*\)\s*\{[\s\S]*?console\.error\s*\(\s*['\"]自定义题型脚本执行错误",
        script_text,
    )
    if outer:
        body = outer.group(1).strip()
        if body:
            return body
    m = re.search(r"try\s*\{([\s\S]*?)\}\s*catch\s*\(", script_text)
    if not m:
        return IRREVERSIBLE_DEFAULTS["genericScript"]
    body = m.group(1).strip()
    return body or IRREVERSIBLE_DEFAULTS["genericScript"]


def _extract_balanced_div_inner(block: str, start_match: re.Match[str]) -> str:
    inner_start = start_match.end()
    # Skip past the '>' closing the opening tag if present
    gt_pos = block.find(">", inner_start)
    if gt_pos == inner_start:
        inner_start = gt_pos + 1
    depth = 1
    token_re = re.compile(r"</?div\b[^>]*>", re.I)
    for m in token_re.finditer(block, inner_start):
        token = m.group(0)
        if token.startswith("</"):
            depth -= 1
            if depth == 0:
                return block[inner_start:m.start()].strip()
        else:
            depth += 1
    return ""


# 将原来的“gc”精准匹配改为了将gc作为子串匹配，这样与模板HTML中的class属性保持一致(比如class="gc xxx")
def _extract_generic_html(block: str) -> str:
    """用稳定的短 class 'gc' 定位，替代原来的完整 class 硬编码，确保rebuild时的稳定性。"""
    gc_match = re.search(r'<div\s+class="(?:[^"]*\s)?gc(?:\s[^"]*)?"', block, flags=re.I)
    if not gc_match:
        return IRREVERSIBLE_DEFAULTS["genericHtml"]
    raw = _extract_balanced_div_inner(block, gc_match)
    if not raw:
        return IRREVERSIBLE_DEFAULTS["genericHtml"]
    return raw.replace("\r\n", "\n").replace("\n", "\\n")


def _is_generic_placeholder(generic: dict[str, str]) -> bool:
    """判断 GENERIC 三段是否仍为模板占位符。"""
    style = generic.get("genericStyle", "")
    html = generic.get("genericHtml", "")
    script = generic.get("genericScript", "")
    return (
        style.strip() in {"", IRREVERSIBLE_DEFAULTS["genericStyle"]}
        and html.strip() in {"", IRREVERSIBLE_DEFAULTS["genericHtml"]}
        and script.strip() in {"", IRREVERSIBLE_DEFAULTS["genericScript"]}
    )


def _extract_generic_fields_from_block(block: str) -> dict[str, str]:
    """从题目 DOM 块（REGION 或 .q）提取 GENERIC 三段源码。"""
    style_match = re.search(r"<style[^>]*>\s*([\s\S]*?)\s*</style>", block, flags=re.S | re.I)
    script_match = re.search(
        r'<script\b[^>]*data-answer-keys="[^"]*"[^>]*>\s*([\s\S]*?)\s*</script>',
        block,
        flags=re.S | re.I,
    )
    return {
        "genericStyle": style_match.group(1).strip() if style_match else IRREVERSIBLE_DEFAULTS["genericStyle"],
        "genericHtml": _extract_generic_html(block),
        "genericScript": _extract_generic_script_body(script_match.group(1))
        if script_match
        else IRREVERSIBLE_DEFAULTS["genericScript"],
    }


def _region_body(block: str) -> str:
    """QUESTION_REGION_START/END 之间的 DOM 片段（不含注释行本身）。"""
    start = block.find("-->")
    if start < 0:
        return block.strip()
    body = block[start + len("-->") :]
    end = body.rfind("<!--")
    if end >= 0:
        body = body[:end]
    return body.strip()


def _question_list_slice(html_text: str) -> str:
    start = html_text.find("QUESTION_LIST_START")
    end = html_text.find("QUESTION_INSERT_POINT")
    if start >= 0 and end > start:
        return html_text[start:end]
    return html_text


def _q_question_blocks(html_text: str) -> list[str]:
    """提取题目列表区域内每个顶层 .q 块（兼容 REGION 空壳、DOM 在外部的情况）。"""
    area = _question_list_slice(html_text)
    return re.findall(
        r'<div class="q"[\s\S]*?(?=<div class="q"|<div class="pb"|<!-- QUESTION_INSERT_POINT|<!-- QUESTION_REGION_START|\Z)',
        area,
        flags=re.S,
    )


def _apply_page_from_block(
    block: str,
    q_uuid: str,
    html_text: str,
    page_by_uuid: dict[str, int],
    page_breaks: list[tuple[int, int]],
) -> None:
    if q_uuid in page_by_uuid:
        return
    page_match = re.search(r'data-page="(\d+)"', block)
    if page_match:
        page_by_uuid[q_uuid] = int(page_match.group(1))
        return
    block_pos = html_text.find(block)
    if block_pos >= 0:
        page_by_uuid[q_uuid] = _infer_page_from_position(block_pos, page_breaks)


def _merge_generic(
    generic_by_uuid: dict[str, dict[str, str]],
    q_uuid: str,
    extracted: dict[str, str],
) -> None:
    """写入 generic_by_uuid；已有非占位内容时不被占位覆盖。"""
    if not q_uuid:
        return
    if q_uuid not in generic_by_uuid or _is_generic_placeholder(generic_by_uuid[q_uuid]):
        if not _is_generic_placeholder(extracted):
            generic_by_uuid[q_uuid] = extracted


def _question_blocks(html_text: str) -> list[str]:
    return re.findall(
        r"(<!-- QUESTION_REGION_START:[\s\S]*?<!-- QUESTION_REGION_END:[\s\S]*?-->)",
        html_text,
        flags=re.S,
    )


def _extract_page_breaks(html_text: str) -> list[tuple[int, int]]:
    """提取所有分页符的位置和页码。

    返回: [(position, page_number), ...] 按位置排序
    """
    page_breaks: list[tuple[int, int]] = []
    # 匹配 data-page-break 属性，支持 data-page-break="1" 或 data-page-break='1' 或 data-page-break=1
    pattern = re.compile(r'<[^>]*data-page-break=["\']?(\d+)["\']?[^>]*>', re.I)
    for m in pattern.finditer(html_text):
        page_breaks.append((m.start(), int(m.group(1))))
    # 按位置排序
    page_breaks.sort(key=lambda x: x[0])
    return page_breaks


def _infer_page_from_position(position: int, page_breaks: list[tuple[int, int]]) -> int:
    """根据题目在 HTML 中的位置推断所属页码。

    逻辑：找到最后一个在题目位置之前的分页符，取其页码；如果没有则默认为 1
    """
    current_page = 1
    for break_pos, page_num in page_breaks:
        if break_pos < position:
            current_page = page_num
        else:
            break
    return current_page


def parse_html_context(html_text: str) -> tuple[dict[str, int], dict[str, dict[str, str]]]:
    """从 HTML 中提取 page 与 GENERIC 三段源码（不解析题目 description，见模块说明）。"""
    page_by_uuid: dict[str, int] = {}
    generic_by_uuid: dict[str, dict[str, str]] = {}

    page_breaks = _extract_page_breaks(html_text)

    # 1) 标准路径：QUESTION_REGION 块内带完整 DOM
    for block in _question_blocks(html_text):
        body = _region_body(block)
        if not body:
            continue
        uuid_match = re.search(r'data-question-uuid="([^"]+)"', body)
        if not uuid_match:
            continue
        q_uuid = uuid_match.group(1)
        _apply_page_from_block(body, q_uuid, html_text, page_by_uuid, page_breaks)

        qtype_match = re.search(r'data-question-type="([^"]+)"', body)
        if not qtype_match or qtype_match.group(1) != "39":
            continue

        _merge_generic(generic_by_uuid, q_uuid, _extract_generic_fields_from_block(body))

    # 2) fallback：REGION 空壳时，从 .q 块按 uuid 提取 page；GENERIC 另取 style/html/script
    for q_block in _q_question_blocks(html_text):
        uuid_match = re.search(r'data-question-uuid="([^"]+)"', q_block)
        if not uuid_match:
            continue
        q_uuid = uuid_match.group(1)
        _apply_page_from_block(q_block, q_uuid, html_text, page_by_uuid, page_breaks)

        type_match = re.search(r'data-question-type="([^"]+)"', q_block)
        if not type_match or type_match.group(1) != "39":
            continue
        _merge_generic(generic_by_uuid, q_uuid, _extract_generic_fields_from_block(q_block))

    return page_by_uuid, generic_by_uuid


def rebuild_spec(
    schema: dict[str, Any],
    *,
    page_by_uuid: dict[str, int] | None = None,
    generic_by_uuid: dict[str, dict[str, str]] | None = None,
    locale: str | None = None,
) -> dict[str, Any]:
    survey = schema.get("survey") or {}
    out_questions: list[dict[str, Any]] = []
    page_by_uuid = page_by_uuid or {}
    generic_by_uuid = generic_by_uuid or {}
    other_labels = other_labels_for_locale(locale)
    default_placeholder = html_dict_for_locale(locale)["placeholder"]

    for qtype, bucket in TYPE_BUCKETS:
        for raw in schema.get(bucket, []) or []:
            if not isinstance(raw, dict):
                continue
            base = _base_question(raw, qtype)
            raw_uuid = str(raw.get("uuid", ""))
            if raw_uuid in page_by_uuid:
                base["page"] = int(page_by_uuid[raw_uuid])
            if qtype == "RADIO":
                options = _normalize_option_labels(raw.get("options"))
                if raw.get("otherOption") or int(raw.get("otherEnabled", 0) or 0) == 1:
                    base["otherOption"] = True
                if options and options[-1] in other_labels:
                    base["otherOption"] = True
                    options = options[:-1]
                base["options"] = options
            elif qtype == "CHECKBOX":
                options = _normalize_option_labels(raw.get("options"))
                if raw.get("otherOption") or int(raw.get("otherEnabled", 0) or 0) == 1:
                    base["otherOption"] = True
                if options and options[-1] in other_labels:
                    base["otherOption"] = True
                    options = options[:-1]
                base["options"] = options
                opt_count = checkbox_option_count(
                    options, other_option=bool(base.get("otherOption"))
                )
                min_c, max_c = normalize_checkbox_choices(
                    raw.get("minChoices"), raw.get("maxChoices"), option_count=opt_count
                )
                base["minChoices"] = min_c
                base["maxChoices"] = max_c
            elif qtype == "TEXTAREA":
                base["placeholder"] = str(raw.get("placeholder", default_placeholder))
                base["minLength"] = int(raw.get("minLength", 0))
                base["maxLength"] = int(raw.get("maxLength", 255))
            elif qtype == "UPLOAD":
                # Preserve the per-question constraints supported by the generator and runtime.
                base["maxFileCount"] = int(raw.get("maxFileCount") or MAX_UPLOAD_FILE_COUNT)
                base["maxFileSize"] = int(raw.get("maxFileSize") or MAX_UPLOAD_FILE_SIZE_KB)
                raw_types = raw.get("fileTypes") if isinstance(raw.get("fileTypes"), list) else None
                normalized = normalize_file_types(raw_types)
                # 全量白名单或未指定时不写 fileTypes，交由 generate 默认放开全部格式
                if normalized and set(normalized) != set(ALLOWED_FILE_EXTENSIONS):
                    base["fileTypes"] = normalized
            elif qtype == "SCALE":
                base["scaleOptions"] = _normalize_scale_like(raw.get("options"))
                scale_labels = raw.get("scaleLabels")
                if scale_labels and isinstance(scale_labels, dict):
                    base["scaleLabels"] = scale_labels
            elif qtype == "MATRIX_SCALE":
                # schema 行/列标题为 rowTitle/columnTitle（兼容旧 title），还原回输入授权格式：
                # rows 为字符串数组、matrixColumns 为 [{title, score, sort}]。
                base["dynamicRows"] = bool(raw.get("dynamicRows", False))
                base["rows"] = [
                    str((x or {}).get("rowTitle", (x or {}).get("title", "")))
                    for x in (raw.get("rows") or []) if isinstance(x, dict)
                ]
                cols = [c for c in (raw.get("columns") or []) if isinstance(c, dict)]
                base["matrixColumns"] = [
                    {
                        "title": str(c.get("columnTitle", c.get("title", ""))),
                        "score": float(c.get("score", 0)),
                        "sort": int(c.get("sort", 0)),
                    }
                    for c in sorted(cols, key=lambda x: int((x or {}).get("sort", 0)))
                ]
            elif qtype == "GENERIC":
                base["answerKeys"] = raw.get("answerKeys") if isinstance(raw.get("answerKeys"), list) else ["answer"]
                uas = raw.get("userAnswersSample")
                base["userAnswersSample"] = uas if isinstance(uas, list) else []
                g = generic_by_uuid.get(raw_uuid) or {}
                base["genericStyle"] = str(g.get("genericStyle", IRREVERSIBLE_DEFAULTS["genericStyle"]))
                base["genericHtml"] = str(g.get("genericHtml", IRREVERSIBLE_DEFAULTS["genericHtml"]))
                base["genericScript"] = str(g.get("genericScript", IRREVERSIBLE_DEFAULTS["genericScript"]))
                base["chartHtml"] = str(raw.get("chartHtml", ""))
            out_questions.append(base)

    out_questions.sort(key=lambda x: int(x.get("_sort", 0)))
    for item in out_questions:
        item.pop("_sort", None)

    return {
        "survey": {
            "title": str(survey.get("title", "")),
            "description": str(survey.get("description", "")),
        },
        "questions": out_questions,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workdir",
        required=True,
        help="current working directory path (the script reads question_schema_generate.json there and overwrites survey_spec.json)",
    )
    parser.add_argument(
        "--locale",
        default=None,
        help='respondent-side UI copy locale (e.g. zh-CN / en-US / es-MX). When omitted, the default zh-CN is used to judge the "Other" option.',
    )
    parser.add_argument(
        "--i18n-dict",
        default=None,
        help="extra locale dictionary JSON ({locale: {key: value}}) for locales the main dictionary does not cover (e.g. Korean ko); see references/i18n-dict.example.json for the key list and examples",
    )
    args = parser.parse_args()

    workdir = Path(args.workdir).resolve()
    if args.i18n_dict:
        load_locale_dict_file(args.i18n_dict)
    warn_if_custom_locale_needed(args.locale, args.i18n_dict)
    schema_path = workdir / "question_schema_generate.json"
    html_path = workdir / "survey-unified-generate.html"
    output_path = workdir / OUTPUT_SPEC_NAME

    schema = load_json(schema_path)
    page_by_uuid: dict[str, int] = {}
    generic_by_uuid: dict[str, dict[str, str]] = {}
    if html_path.exists():
        page_by_uuid, generic_by_uuid = parse_html_context(html_path.read_text(encoding="utf-8"))
    rebuilt = rebuild_spec(
        schema,
        page_by_uuid=page_by_uuid,
        generic_by_uuid=generic_by_uuid,
        locale=args.locale,
    )
    output_path.write_text(json.dumps(rebuilt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Overwritten: {output_path.resolve()}")


if __name__ == "__main__":
    main()
