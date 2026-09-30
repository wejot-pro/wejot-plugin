#!/usr/bin/env python3
"""向已有问卷产物中增量追加题目（GENERIC / 标准题型均可）。

用法：
    python append_questions_to_survey.py --spec append_spec.json [--target-dir /path/to/output]

--spec 格式（与 generate_standard_survey.py 的 questions 数组格式一致）：
{
  "questions": [
    {"type": "GENERIC", "title": "NPS 评分", "code": "nps_score", ...}
  ]
}

注意：spec 中不需要 survey 字段（标题/描述沿用已有产物）。

默认尾部追加（无 --anchor-comment / --insert-page-end）时，新题物理位置在 HTML 最后一页；
若 append_spec 中 page 与最后一页不一致，脚本会静默改为最后一页并写回 HTML data-page。
往历史页中间加题请使用 --insert-page-end N。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import replace
from pathlib import Path

from bs4 import BeautifulSoup, Comment

# 复用 generate_standard_survey 中的核心函数
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_standard_survey import (
    MINIMAL_SPEC_TEMPLATE_PATH,
    SYSTEM_JSON_TEMPLATE_PATH,
    QuestionSpec,
    build_question_html,
    build_schema,
    gen_uuid,
    load_json,
    load_system_json_template,
    parse_questions,
    schema_to_question_specs,
    generate_option_value_constants,
    _ensure_survey_ui_css,
    _inject_constants_into_survey_ui_js,
    validate_spec_structure,
    validate_spec_chart_html,
    _TYPE_TO_SCHEMA_BUCKET,
)
from survey_ui_i18n import load_locale_dict_file, warn_if_custom_locale_needed

def _find_existing_max(schema: dict) -> tuple[int, int]:
    """从已有 JSON schema 中提取最大 sort 值和最大 question index。"""
    max_sort = 0
    total_count = 0
    for bucket_key in _TYPE_TO_SCHEMA_BUCKET.values():
        for item in schema.get(bucket_key, []):
            total_count += 1
            sort_val = item.get("sort", 0)
            if sort_val > max_sort:
                max_sort = sort_val
    return max_sort, total_count


_QUESTION_LIST_REGION_RE = re.compile(
    r"<!-- QUESTION_LIST_START:.*?-->(.*?)<!-- QUESTION_INSERT_POINT:.*?-->",
    flags=re.S,
)
_PAGE_BREAK_RE = re.compile(r'<div\b[^>]*data-page-break="(\d+)"[^>]*>', flags=re.I)


def _question_list_region(html: str) -> str | None:
    m = _QUESTION_LIST_REGION_RE.search(html)
    return m.group(1) if m else None


def _infer_last_dom_page(html: str) -> int:
    """与 validate_standard_survey._validate_dom_page_placement 一致：最后一处 data-page-break 的页码；无分页符视为第 1 页。"""
    region = _question_list_region(html)
    if region is None:
        return 1
    breaks = [int(m.group(1)) for m in _PAGE_BREAK_RE.finditer(region)]
    return breaks[-1] if breaks else 1


def _align_tail_append_pages(
    questions: list[QuestionSpec],
    last_dom_page: int,
) -> list[QuestionSpec]:
    """默认尾部追加：将 spec.page 对齐为 HTML 最后一页，避免 data-page 与 DOM 分段不一致。"""
    aligned: list[QuestionSpec] = []
    for q in questions:
        if q.page != last_dom_page:
            aligned.append(replace(q, page=last_dom_page))
        else:
            aligned.append(q)
    return aligned


def _reindex_new_questions(
    questions: list[QuestionSpec],
    start_sort: int,
    start_index: int,
) -> list[QuestionSpec]:
    """为追加的题目重新分配 sort 和 index（不修改原对象，返回新列表）。"""
    result = []
    for i, q in enumerate(questions):
        new_q = QuestionSpec(
            title=q.title,
            qtype=q.qtype,
            required=q.required,
            page=q.page,
            code=q.code,
            sort=start_sort + (i + 1) * 1000,
            description=q.description,
            uid=q.uid or gen_uuid(),
            options=q.options,
            scale_options=q.scale_options,
            matrix_rows=q.matrix_rows,
            matrix_columns=q.matrix_columns,
            max_choices=q.max_choices,
            min_choices=q.min_choices,
            placeholder=q.placeholder,
            min_length=q.min_length,
            max_length=q.max_length,
            max_file_count=q.max_file_count,
            max_file_size=q.max_file_size,
            file_types=q.file_types,
            answer_keys=q.answer_keys,
            user_answers_sample=q.user_answers_sample,
            chart_html=q.chart_html,
            generic_style=q.generic_style,
            generic_html=q.generic_html,
            generic_script=q.generic_script,
        )
        result.append(new_q)
    return result


def _merge_json(
    existing_schema: dict,
    new_questions: list[QuestionSpec],
    tmpl_json: dict,
    *,
    locale: str | None = None,
) -> dict:
    """将新题目的 JSON 追加到已有 schema 的对应 bucket 中。"""
    # 构建一个临时 spec 用于 build_schema
    temp_spec = {
        "survey": existing_schema.get("survey", {"title": "", "description": ""}),
        "questions": [],  # not used by build_schema directly
    }
    # 用 build_schema 为新题目生成 JSON
    new_schema = build_schema(temp_spec, tmpl_json, new_questions, locale=locale)

    # 合并到已有 schema
    for bucket_key in _TYPE_TO_SCHEMA_BUCKET.values():
        new_items = new_schema.get(bucket_key, [])
        if new_items:
            if bucket_key not in existing_schema:
                existing_schema[bucket_key] = []
            existing_schema[bucket_key].extend(new_items)

    return existing_schema


def _normalize_text_question_type(schema: dict) -> None:
    """历史兼容：把 textQuestions 中的 INPUT 统一归一为 TEXTAREA。"""
    for item in schema.get("textQuestions", []) or []:
        if isinstance(item, dict) and str(item.get("type", "")).upper() == "INPUT":
            item["type"] = "TEXTAREA"


def _schema_items_by_uuid(schema: dict) -> dict[str, dict]:
    """根据uuid来索引某一类的题"""
    out: dict[str, dict] = {}
    for bucket_key in _TYPE_TO_SCHEMA_BUCKET.values():
        for item in schema.get(bucket_key, []) or []:
            if isinstance(item, dict) and item.get("uuid"):
                out[str(item["uuid"])] = item
    return out


def _normalize_question_order_after_anchor_insert(html: str, schema: dict) -> tuple[str, dict]:
    """锚点在中间插题后，原来的 index/sort 与 DOM 实际顺序不一致；按 DOM 顺序重排，使其保持一致。"""
    # Phase A: 用 BS4 发现题目 div 和注释节点（仅用于发现，不用于回写；
    # str(soup) 会重排属性顺序、改变布尔属性格式、丢失缩进，因此后续修改仍作用于原始 html 字符串）
    soup = BeautifulSoup(html, "html.parser")
    q_divs = soup.find_all("div", class_="q")
    ordered_uuids = [div.get("data-question-uuid") for div in q_divs if div.get("data-question-uuid")]
    if not ordered_uuids:
        raise ValueError("No .q[data-question-uuid] question nodes found in the HTML; cannot reorder questions")

    schema_by_uuid = _schema_items_by_uuid(schema)
    missing_in_schema = [u for u in ordered_uuids if u not in schema_by_uuid]
    missing_in_html = [u for u in schema_by_uuid if u not in set(ordered_uuids)]
    if missing_in_schema or missing_in_html:
        raise ValueError(
            "HTML/schema question sets are inconsistent: "
            f"missing_in_schema={missing_in_schema}, missing_in_html={missing_in_html}"
        )

    order_by_uuid = {uuid: idx for idx, uuid in enumerate(ordered_uuids, start=1)}
    for uuid, item in schema_by_uuid.items():
        item["sort"] = order_by_uuid[uuid] * 1000

    # 用 BS4 注释节点构建 START comment → UUID 映射
    comments = soup.find_all(string=lambda s: isinstance(s, Comment))
    start_comments = [c for c in comments if "QUESTION_REGION_START" in str(c)]
    comment_uuid_pairs: list[tuple[str, str]] = []
    for start_c in start_comments:
        next_div = start_c.find_next("div", class_="q")
        if next_div and next_div.get("data-question-uuid"):
            end_c = start_c.find_next(
                string=lambda s: isinstance(s, Comment) and "QUESTION_REGION_END" in str(s)
            )
            comment_uuid_pairs.append((next_div["data-question-uuid"], str(end_c).strip() if end_c else ""))

    # Phase B: 逐 UUID 在原始 HTML 上做定向字符串修改（替代原先 re.sub 整体匹配
    # question region block 的回调模式——UUID 全局唯一，以 UUID 为锚点的 count=1 替换
    # 不会产生误匹配，且避免了嵌套 regex 回调的可读性问题）
    for uuid, new_idx in order_by_uuid.items():
        escaped_uuid = re.escape(uuid)

        # 更新 data-question-index（UUID 作用域，避免误匹配）
        html = re.sub(
            rf'(data-question-uuid="{escaped_uuid}"[^>]*?)data-question-index="\d+"',
            rf'\g<1>data-question-index="{new_idx}"',
            html,
            count=1,
        )

        # 更新 QUESTION_REGION_START 注释中的 index
        html = re.sub(
            rf"(<!-- QUESTION_REGION_START: index=)\d+(.*?{escaped_uuid}.*?-->)",
            rf"\g<1>{new_idx}\g<2>",
            html,
            count=1,
        )

        # 更新 <span data-q-number> 文本（UUID 位置之后搜索）
        uuid_pos = html.find(uuid)
        if uuid_pos >= 0:
            span_match = re.search(r"(<span data-q-number>)\d{2}(</span>)", html[uuid_pos:])
            if span_match:
                abs_start = uuid_pos + span_match.start(1) + len(span_match.group(1))
                html = html[:abs_start] + f"{new_idx:02d}" + html[abs_start + 2:]

        # 更新 QUESTION_REGION_END 注释中的 index
        for pair_uuid, end_text in comment_uuid_pairs:
            if pair_uuid == uuid and end_text:
                new_end = re.sub(r"index=\d+", f"index={new_idx}", end_text)
                html = html.replace(f"<!-- {end_text} -->", f"<!-- {new_end} -->", 1)
                break

    return html, schema


def _find_page_end_insert_position(html: str, target_page: int) -> int:
    """查找指定页面末尾的插入位置。

    返回在下一个 data-page-break 之前的位置，若目标页面是最后一页则返回 QUESTION_INSERT_POINT 之前的位置。
    """
    # 提取 QUESTION_LIST_START ~ QUESTION_INSERT_POINT 区间
    region_match = re.search(
        r'(<!-- QUESTION_LIST_START:.*?-->)(.*?)(<!-- QUESTION_INSERT_POINT:.*?-->)',
        html,
        flags=re.S,
    )
    if not region_match:
        raise ValueError("The QUESTION_LIST_START ~ QUESTION_INSERT_POINT region was not found in the existing HTML")

    region_start = region_match.start(2)
    region = region_match.group(2)

    # 查找所有 data-page-break 的位置
    page_break_pattern = re.compile(r'<div\b[^>]*data-page-break="(\d+)"[^>]*>', flags=re.I)
    page_breaks = []
    for m in page_break_pattern.finditer(region):
        page_breaks.append((int(m.group(1)), region_start + m.start()))

    # 查找目标页面的下一个页面分隔符位置
    next_page_break_pos = None
    for page_num, pos in page_breaks:
        if page_num > target_page:
            next_page_break_pos = pos
            break

    if next_page_break_pos is not None:
        return next_page_break_pos

    # 目标页面是最后一页，返回 QUESTION_INSERT_POINT 之前的位置
    insert_point_match = re.search(r'<!-- QUESTION_INSERT_POINT:.*?-->', html)
    if not insert_point_match:
        raise ValueError("The QUESTION_INSERT_POINT marker was not found in the existing HTML")
    return insert_point_match.start()


def _append_html(
    existing_html: str,
    new_questions: list[QuestionSpec],
    start_index: int,
    *,
    tmpl_json: dict | None = None,
    anchor_comment: str | None = None,
    insert_page_end: int | None = None,
    locale: str | None = None,
) -> str:
    """将新题目的 HTML 插入到锚点之前（默认 QUESTION_INSERT_POINT）。"""
    new_blocks = [
        build_question_html(q, start_index + i, locale=locale)
        for i, q in enumerate(new_questions, start=1)
    ]
    new_html_fragment = "\n".join(new_blocks)

    # 页面末尾插入模式
    if insert_page_end is not None:
        insert_pos = _find_page_end_insert_position(existing_html, insert_page_end)
        return existing_html[:insert_pos] + new_html_fragment + "\n    " + existing_html[insert_pos:]

    # 默认尾部追加：在 QUESTION_INSERT_POINT 标记之前插入
    pattern = r"(<!-- QUESTION_INSERT_POINT:.*?-->)"
    error_hint = "The <!-- QUESTION_INSERT_POINT --> marker was not found in the existing HTML"
    if anchor_comment:
        pattern = rf"(<!--\s*{re.escape(anchor_comment)}\s*-->)"
        error_hint = f'Custom anchor comment <!-- {anchor_comment} -->'
    match = re.search(pattern, existing_html)
    if not match:
        raise ValueError(error_hint)

    insert_pos = match.start()
    return existing_html[:insert_pos] + new_html_fragment + "\n    " + existing_html[insert_pos:]


def main() -> None:
    parser = argparse.ArgumentParser(description="Append questions to an existing survey")
    parser.add_argument("--spec", required=True, help="path to the spec JSON of the questions to append")
    parser.add_argument("--target-dir", default=None, help="existing artifact directory; defaults to the spec directory")
    parser.add_argument(
        "--anchor-comment",
        default=None,
        help="optional: custom HTML comment anchor string (the script matches <!-- <anchor> --> and inserts questions before it)",
    )
    parser.add_argument(
        "--insert-page-end",
        type=int,
        default=None,
        help="optional: page number; insert the new questions at the end of that page (before the next data-page-break)",
    )
    parser.add_argument(
        "--locale",
        default=None,
        help="respondent-side UI copy locale (e.g. zh-CN / en-US / es-MX). When omitted, the default zh-CN shell copy is kept.",
    )
    parser.add_argument(
        "--i18n-dict",
        default=None,
        help="extra locale dictionary JSON ({locale: {key: value}}) for locales the main dictionary does not cover (e.g. Korean ko); see references/i18n-dict.example.json for the key list and examples",
    )
    args = parser.parse_args()

    spec_path = Path(args.spec)
    if args.i18n_dict:
        load_locale_dict_file(args.i18n_dict)
    warn_if_custom_locale_needed(args.locale, args.i18n_dict)
    target_dir = Path(args.target_dir) if args.target_dir else spec_path.parent

    # 检查已有产物
    json_path = target_dir / "question_schema_generate.json"
    html_path = target_dir / "survey-unified-generate.html"

    if not json_path.exists():
        print(f"Error: existing JSON artifact not found: {json_path}", file=sys.stderr)
        sys.exit(1)
    if not html_path.exists():
        print(f"Error: existing HTML artifact not found: {html_path}", file=sys.stderr)
        sys.exit(1)

    # 加载已有产物
    existing_schema = load_json(json_path)
    _normalize_text_question_type(existing_schema)
    existing_html = html_path.read_text(encoding="utf-8")

    # 加载追加 spec
    append_spec = load_json(spec_path)
    try:
        # append 场景只校验 questions，不检查 survey 字段是否存在及其内容
        validate_spec_structure({"questions": append_spec.get("questions")}, require_survey=False)
        validate_spec_chart_html({"questions": append_spec.get("questions")})
    except ValueError as e:
        print(f"Error: the append spec structure is invalid.\n{e}", file=sys.stderr)
        print(
            "Fix it according to the spec examples before calling the append script: "
            f"{MINIMAL_SPEC_TEMPLATE_PATH}",
            file=sys.stderr,
        )
        sys.exit(1)
    if not append_spec.get("questions"):
        print(
            "Note: the appended spec has 0 questions, so no questions will be added; the existing artifacts remain unchanged.",
            file=sys.stderr,
        )

    # 为 parse_questions 补充 survey 字段（沿用已有）
    if "survey" not in append_spec:
        append_spec["survey"] = existing_schema.get("survey", {"title": "", "description": ""})

    # 解析新题目
    new_questions = parse_questions(append_spec, locale=args.locale)

    is_default_tail_append = args.insert_page_end is None and not args.anchor_comment
    if is_default_tail_append and new_questions:
        last_dom_page = _infer_last_dom_page(existing_html)
        new_questions = _align_tail_append_pages(new_questions, last_dom_page)

    # 验证页面末尾插入模式下题目的 page 属性
    if args.insert_page_end is not None:
        for q in new_questions:
            if q.page != args.insert_page_end:
                print(
                    f"Error: in --insert-page-end={args.insert_page_end} mode, "
                    f"question \"{q.title}\" has page={q.page}, which differs from the "
                    "target page; the page of every appended question must equal the "
                    "target page",
                    file=sys.stderr,
                )
                sys.exit(1)

    # 计算续接参数
    max_sort, total_count = _find_existing_max(existing_schema)
    new_questions = _reindex_new_questions(new_questions, max_sort, total_count)

    # 加载模板（用于 build_schema 中的默认值）
    tmpl_json = load_system_json_template()

    # 1. 合并 JSON
    merged_schema = _merge_json(existing_schema, new_questions, tmpl_json, locale=args.locale)
    _normalize_text_question_type(merged_schema)

    # 2. 追加 HTML
    merged_html = _append_html(
        existing_html,
        new_questions,
        total_count,
        tmpl_json=tmpl_json,
        anchor_comment=args.anchor_comment,
        insert_page_end=args.insert_page_end,
        locale=args.locale,
    )

    # 2.1 若使用自定义锚点或页面末尾插入，按 DOM 顺序归一化 index/sort
    if args.anchor_comment or args.insert_page_end is not None:
        merged_html, merged_schema = _normalize_question_order_after_anchor_insert(merged_html, merged_schema)

    # 3. 刷新 survey-ui.js 常量，并确保 survey-ui.css 存在（与 generate_standard_survey 对称）
    # 追加题目后总题数/选项发生变化，survey-ui.js 中的 Qn_UUID / Qn_OPT_n 等常量必须同步刷新，
    # 否则 LLM 后续写逻辑代码时引用的常量与实际 DOM 不匹配。
    all_questions = schema_to_question_specs(merged_schema, locale=args.locale)
    constants = generate_option_value_constants(all_questions, locale=args.locale)
    _ensure_survey_ui_css(target_dir)
    _inject_constants_into_survey_ui_js(target_dir, constants)

    # 写回产物
    json_path.write_text(json.dumps(merged_schema, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(merged_html, encoding="utf-8")

    print(f"✓ Appended {len(new_questions)} question(s)")
    print(f"  - updated: {json_path}")
    print(f"  - updated: {html_path}")
    print(f"  - current total questions: {total_count + len(new_questions)}")


if __name__ == "__main__":
    main()
