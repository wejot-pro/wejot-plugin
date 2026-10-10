#!/usr/bin/env python3
"""向已有自由模式问卷增量追加题目（保留自定义 CSS/JS 与骨架核心结构）。

用法:
    python append_questions_to_free_mode_survey.py \\
      --spec append_spec.json \\
      [--target-dir /path/to/workdir]

--spec 仅需 questions 数组（格式同 minimal_survey_spec.json），不要求 survey 字段。
追加后自动调用 validate_free_mode_survey.py 校验。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Comment

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from generate_free_mode_skeleton import (  # noqa: E402
    _EVENT_HANDLER_FENCE,
    _JS_REGION_BEGIN,
    _JS_REGION_END,
    _build_js_answer_entry,
    _build_js_event_handler,
    _build_question_html,
    _ensure_survey_ui_css,
)
from generate_standard_survey import (  # noqa: E402
    MINIMAL_SPEC_TEMPLATE_PATH,
    SYSTEM_JSON_TEMPLATE_PATH,
    QuestionSpec,
    _TYPE_TO_SCHEMA_BUCKET,
    build_schema,
    gen_uuid,
    load_json,
    load_system_json_template,
    parse_questions,
    validate_spec_structure,
    validate_spec_chart_html,
)
from survey_ui_i18n import load_locale_dict_file, warn_if_custom_locale_needed  # noqa: E402

_VALIDATE_SCRIPT = SCRIPTS_DIR / "validate_free_mode_survey.py"
_REF_SCHEMA_TEMPLATE = SCRIPTS_DIR.parent / "references" / "question_schema_generate.json"
_FREE_MODE_MARKER = "LLM 自定义 CSS 区域 BEGIN"
_INSERT_POINT_PATTERN = re.compile(r"<!--\s*QUESTION_INSERT_POINT:.*?-->", re.S)
_BUILD_ANSWERS_PATTERN = re.compile(
    r"(function buildAnswers\(\)\s*\{\s*return\s*\[)(.*?)(\]\s*;\s*\}\s*\n\s*function submitSurvey)",
    re.S,
)


def _resolve_script_target(html: str, target_dir: Path) -> tuple[str, Path | None]:
    """优先 patch survey-ui.js；legacy 仅 HTML 含 buildAnswers 时 fallback。"""
    js_path = target_dir / "survey-ui.js"
    if js_path.is_file():
        js_content = js_path.read_text(encoding="utf-8")
        if _EVENT_HANDLER_FENCE in js_content and "function buildAnswers()" in js_content:
            return js_content, js_path
    if _EVENT_HANDLER_FENCE in html and "function buildAnswers()" in html:
        return html, None
    return "", None


def _has_free_mode_script_structure(html: str, target_dir: Path) -> bool:
    _, target = _resolve_script_target(html, target_dir)
    if target is not None:
        return True
    return _EVENT_HANDLER_FENCE in html and "function buildAnswers()" in html


def _load_schema_template() -> dict[str, Any]:
    tmpl = load_system_json_template()
    if tmpl:
        return tmpl
    if _REF_SCHEMA_TEMPLATE.is_file():
        return load_json(_REF_SCHEMA_TEMPLATE)
    return {}


def _is_free_mode_html(html: str) -> bool:
    if 'data-survey-mode="free"' in html:
        return True
    if _FREE_MODE_MARKER in html:
        return True
    return False


def _is_standard_mode_html(html: str) -> bool:
    return not _is_free_mode_html(html)


def _find_existing_max(schema: dict[str, Any]) -> tuple[int, int]:
    max_sort = 0
    total_count = 0
    for bucket_key in _TYPE_TO_SCHEMA_BUCKET.values():
        for item in schema.get(bucket_key, []) or []:
            total_count += 1
            sort_val = int(item.get("sort", 0) or 0)
            if sort_val > max_sort:
                max_sort = sort_val
    return max_sort, total_count


def _reindex_new_questions(
    questions: list[QuestionSpec],
    start_sort: int,
) -> list[QuestionSpec]:
    result: list[QuestionSpec] = []
    for i, q in enumerate(questions):
        result.append(
            QuestionSpec(
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
        )
    return result


def _merge_json(
    existing_schema: dict[str, Any],
    new_questions: list[QuestionSpec],
    tmpl_json: dict[str, Any],
    *,
    locale: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """合并 schema，并返回本次新增的题目对象列表（来自 build_schema）。"""
    survey = existing_schema.get("survey", {"title": "", "description": ""})
    temp_spec = {"survey": survey, "questions": []}
    new_schema = build_schema(temp_spec, tmpl_json, new_questions, locale=locale)

    new_items: list[dict[str, Any]] = []
    for bucket_key in _TYPE_TO_SCHEMA_BUCKET.values():
        items = new_schema.get(bucket_key, []) or []
        if items:
            if bucket_key not in existing_schema:
                existing_schema[bucket_key] = []
            existing_schema[bucket_key].extend(items)
            new_items.extend(items)

    new_items.sort(key=lambda q: int(q.get("sort", 0) or 0))
    return existing_schema, new_items


def _normalize_text_question_type(schema: dict[str, Any]) -> None:
    for item in schema.get("textQuestions", []) or []:
        if isinstance(item, dict) and str(item.get("type", "")).upper() == "INPUT":
            item["type"] = "TEXTAREA"


def _schema_items_by_uuid(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for bucket_key in _TYPE_TO_SCHEMA_BUCKET.values():
        for item in schema.get(bucket_key, []) or []:
            if isinstance(item, dict) and item.get("uuid"):
                out[str(item["uuid"])] = item
    return out


def _find_page_end_insert_position(html: str, target_page: int) -> int:
    insert_match = _INSERT_POINT_PATTERN.search(html)
    if not insert_match:
        raise ValueError("The <!-- QUESTION_INSERT_POINT --> marker was not found in the existing HTML")

    region_end = insert_match.start()
    region = html[:region_end]
    page_break_pattern = re.compile(
        r'<div\b[^>]*\bdata-page-break=["\']?(\d+)["\']?[^>]*>',
        flags=re.I,
    )
    for m in page_break_pattern.finditer(region):
        page_num = int(m.group(1))
        if page_num > target_page:
            return m.start()
    return region_end


def _append_question_dom(
    existing_html: str,
    new_items: list[dict[str, Any]],
    start_index: int,
    page_by_code: dict[str, int],
    *,
    anchor_comment: str | None = None,
    insert_page_end: int | None = None,
    locale: str | None = None,
) -> str:
    blocks = [
        _build_question_html(q, start_index + i, page_by_code, locale=locale)
        for i, q in enumerate(new_items, start=1)
    ]
    fragment = "\n\n".join(blocks) + "\n\n    "

    if insert_page_end is not None:
        pos = _find_page_end_insert_position(existing_html, insert_page_end)
        return existing_html[:pos] + fragment + existing_html[pos:]

    if anchor_comment:
        pattern = rf"(<!--\s*{re.escape(anchor_comment)}\s*-->)"
        match = re.search(pattern, existing_html)
        if not match:
            raise ValueError(f'The custom anchor <!-- {anchor_comment} --> was not found in the existing HTML')
        pos = match.start()
        return existing_html[:pos] + fragment + existing_html[pos:]

    match = _INSERT_POINT_PATTERN.search(existing_html)
    if not match:
        raise ValueError("The <!-- QUESTION_INSERT_POINT --> marker was not found in the existing HTML")
    pos = match.start()
    return existing_html[:pos] + fragment + existing_html[pos:]


def _patch_event_handlers(script: str, new_handlers: list[str]) -> str:
    if not new_handlers:
        return script
    block = "\n\n".join(new_handlers) + "\n\n    "
    idx = script.find("function buildAnswers()")
    if idx < 0:
        raise ValueError("function buildAnswers() not found; cannot append event-handling logic")
    return script[:idx] + block + script[idx:]


def _warn_unsafe_pagination_pattern(script: str) -> None:
    """检测自定义区是否对全卷 data-option 绑翻页（仅 warning，不阻断）。"""
    m = re.search(
        rf"{re.escape(_JS_REGION_BEGIN)}(.*?){re.escape(_JS_REGION_END)}",
        script,
        re.DOTALL,
    )
    if not m:
        m = re.search(
            r"LLM 自定义交互逻辑区域 BEGIN(.*?)LLM 自定义交互逻辑区域 END",
            script,
            re.DOTALL,
        )
    if not m:
        return
    block = m.group(1)
    if "goToNextPage" not in block and "goToNext" not in block:
        return
    if not re.search(
        r"querySelectorAll\s*\(\s*['\"][^'\"]*\[data-option\]",
        block,
    ):
        return
    if re.search(r"data-question-type", block) and re.search(
        r"['\"]8['\"]|['\"]9['\"]",
        block,
    ):
        return
    print(
        "⚠ Warning: the custom area seems to bind auto page-turning to all [data-option] "
        "elements; scale/matrix questions may be triggered by mistake. "
        "Only type=8 (RADIO) may auto page-turn; see the F1/F2 contract.",
        file=sys.stderr,
    )


def _patch_build_answers(script: str, new_entries: list[str]) -> str:
    if not new_entries:
        return script
    m = _BUILD_ANSWERS_PATTERN.search(script)
    if not m:
        raise ValueError("The buildAnswers() return array was not found; cannot append submission entries")
    body = m.group(2).rstrip()
    joined = ",\n".join(new_entries)
    if body.strip():
        body = body + ",\n" + joined
    else:
        body = "\n" + joined
    return script[: m.start()] + m.group(1) + body + m.group(3) + script[m.end() :]


def _normalize_question_order_after_anchor_insert(
    html: str,
    schema: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    q_divs = [
        d
        for d in soup.find_all("div")
        if d.has_attr("data-question") and d.get("data-question-uuid")
    ]
    ordered_uuids = [str(d["data-question-uuid"]) for d in q_divs]
    if not ordered_uuids:
        raise ValueError("No [data-question][data-question-uuid] question nodes found in the HTML")

    schema_by_uuid = _schema_items_by_uuid(schema)
    missing_in_schema = [u for u in ordered_uuids if u not in schema_by_uuid]
    missing_in_html = [u for u in schema_by_uuid if u not in set(ordered_uuids)]
    if missing_in_schema or missing_in_html:
        raise ValueError(
            "HTML/schema question sets mismatch: "
            f"missing_in_schema={missing_in_schema}, missing_in_html={missing_in_html}"
        )

    order_by_uuid = {uuid: idx for idx, uuid in enumerate(ordered_uuids, start=1)}
    for uuid, item in schema_by_uuid.items():
        item["sort"] = order_by_uuid[uuid] * 1000

    comments = soup.find_all(string=lambda s: isinstance(s, Comment))
    start_comments = [c for c in comments if "QUESTION_REGION_START" in str(c)]
    comment_uuid_pairs: list[tuple[str, str]] = []
    for start_c in start_comments:
        next_div = start_c.find_next("div", attrs={"data-question": True})
        if next_div and next_div.get("data-question-uuid"):
            end_c = start_c.find_next(
                string=lambda s: isinstance(s, Comment) and "QUESTION_REGION_END" in str(s)
            )
            comment_uuid_pairs.append(
                (str(next_div["data-question-uuid"]), str(end_c).strip() if end_c else "")
            )

    for uuid, new_idx in order_by_uuid.items():
        escaped_uuid = re.escape(uuid)
        html = re.sub(
            rf'(data-question-uuid="{escaped_uuid}"[^>]*?)data-question-index="\d+"',
            rf'\g<1>data-question-index="{new_idx}"',
            html,
            count=1,
        )
        html = re.sub(
            rf"(<!-- QUESTION_REGION_START: index=)\d+(.*?{escaped_uuid}.*?-->)",
            rf"\g<1>{new_idx}\g<2>",
            html,
            count=1,
        )
        uuid_pos = html.find(uuid)
        if uuid_pos >= 0:
            for tag in ("b", "span"):
                span_match = re.search(
                    rf"(<{tag} data-q-number>)\d{{2}}(</{tag}>)",
                    html[uuid_pos:],
                )
                if span_match:
                    abs_start = uuid_pos + span_match.start(1) + len(span_match.group(1))
                    html = html[:abs_start] + f"{new_idx:02d}" + html[abs_start + 2 :]
                    break
        for pair_uuid, end_text in comment_uuid_pairs:
            if pair_uuid == uuid and end_text:
                new_end = re.sub(r"index=\d+", f"index={new_idx}", end_text)
                html = html.replace(f"<!-- {end_text} -->", f"<!-- {new_end} -->", 1)
                break

    return html, schema


def main() -> int:
    parser = argparse.ArgumentParser(description="Append questions to an existing free-mode survey")
    parser.add_argument("--spec", required=True, help="path to the spec JSON of the questions to append")
    parser.add_argument("--target-dir", default=None, help="existing artifact directory; defaults to the --spec directory")
    parser.add_argument(
        "--anchor-comment",
        default=None,
        help="optional: insert new questions before the <!-- anchor --> comment",
    )
    parser.add_argument(
        "--insert-page-end",
        type=int,
        default=None,
        help="optional: insert at the end of the given page (before the next data-page-break)",
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="skip validate_free_mode_survey.py (for debugging; do not enable in normal use)",
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
    json_path = target_dir / "question_schema_generate.json"
    html_path = target_dir / "survey-unified-generate.html"

    if not json_path.exists():
        print(f"Error: not found: {json_path}", file=sys.stderr)
        return 1
    if not html_path.exists():
        print(f"Error: not found: {html_path}", file=sys.stderr)
        return 1

    existing_schema = load_json(json_path)
    _normalize_text_question_type(existing_schema)
    existing_html = html_path.read_text(encoding="utf-8")

    if _is_standard_mode_html(existing_html):
        print(
            "Error: a standard-mode survey page was detected (the HTML has no free-mode marker "
            'data-survey-mode="free"'
            "); use the standard-mode append-questions flow.",
            file=sys.stderr,
        )
        return 1
    if not _has_free_mode_script_structure(existing_html, target_dir):
        print(
            "Error: the free-mode skeleton core structure is missing (base event-handling "
            "area / buildAnswers). First run generate_free_mode_skeleton.py to generate the "
            "skeleton, or make sure survey-ui.js exists.",
            file=sys.stderr,
        )
        return 1

    # CSS 缺失时补自由模式空骨架（不覆盖已有定制样式；不拷标准模板）
    _ensure_survey_ui_css(target_dir)

    append_spec = load_json(spec_path)
    try:
        validate_spec_structure({"questions": append_spec.get("questions")}, require_survey=False)
        validate_spec_chart_html({"questions": append_spec.get("questions")})
    except ValueError as e:
        print(f"Error: the append spec structure is invalid.\n{e}", file=sys.stderr)
        print(f"Reference: {MINIMAL_SPEC_TEMPLATE_PATH}", file=sys.stderr)
        return 1

    questions_raw = append_spec.get("questions") or []
    if not questions_raw:
        print("Note: questions is empty; nothing was appended.", file=sys.stderr)
        return 0

    if "survey" not in append_spec:
        append_spec["survey"] = existing_schema.get("survey", {"title": "", "description": ""})

    new_questions = parse_questions(append_spec, locale=args.locale)
    if args.insert_page_end is not None:
        for q in new_questions:
            if q.page != args.insert_page_end:
                print(
                    f"Error: in --insert-page-end={args.insert_page_end} mode, "
                    f"question \"{q.title}\" has page={q.page}, which must equal the target page",
                    file=sys.stderr,
                )
                return 1

    max_sort, total_count = _find_existing_max(existing_schema)
    new_questions = _reindex_new_questions(new_questions, max_sort)
    page_by_code = {q.code: int(q.page) for q in new_questions}

    tmpl_json = _load_schema_template()
    merged_schema, new_schema_items = _merge_json(
        existing_schema, new_questions, tmpl_json, locale=args.locale
    )
    _normalize_text_question_type(merged_schema)

    merged_html = _append_question_dom(
        existing_html,
        new_schema_items,
        total_count,
        page_by_code,
        anchor_comment=args.anchor_comment,
        insert_page_end=args.insert_page_end,
        locale=args.locale,
    )
    new_answer_entries = [_build_js_answer_entry(q) for q in new_schema_items]
    new_event_handlers = [_build_js_event_handler(q) for q in new_schema_items]

    script_content, script_path = _resolve_script_target(merged_html, target_dir)
    patched_script = _patch_event_handlers(script_content, new_event_handlers)
    patched_script = _patch_build_answers(patched_script, new_answer_entries)

    if script_path is not None:
        script_path.write_text(patched_script, encoding="utf-8")
        _warn_unsafe_pagination_pattern(patched_script)
    else:
        merged_html = patched_script
        _warn_unsafe_pagination_pattern(merged_html)

    if args.anchor_comment or args.insert_page_end is not None:
        merged_html, merged_schema = _normalize_question_order_after_anchor_insert(
            merged_html, merged_schema
        )

    json_path.write_text(
        json.dumps(merged_schema, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    html_path.write_text(merged_html, encoding="utf-8")

    print(f"✓ Appended {len(new_schema_items)} question(s)")
    print(f"  - updated: {json_path}")
    print(f"  - updated: {html_path}")
    if script_path is not None:
        print(f"  - updated: {script_path}")
    print(f"  - current total questions: {total_count + len(new_schema_items)}")

    if not args.skip_validate:
        print("Running validate_free_mode_survey.py ...")
        proc = subprocess.run(
            [
                sys.executable,
                str(_VALIDATE_SCRIPT),
                "--schema",
                str(json_path),
                "--html",
                str(html_path),
                "--dir",
                str(target_dir),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.stdout.strip():
            print(proc.stdout.strip())
        if proc.stderr.strip():
            print(proc.stderr.strip(), file=sys.stderr)
        if proc.returncode != 0:
            print("Validation failed; fix the artifacts according to the errors above.", file=sys.stderr)
            return proc.returncode
        print("✓ validate_free_mode_survey.py passed (the *spec.json draft was cleaned up by the validator)")
    elif spec_path.is_file() and spec_path.name.endswith("spec.json"):
        if spec_path.resolve().parent == target_dir.resolve():
            for path in sorted(target_dir.glob("*spec.json")):
                if path.is_file():
                    path.unlink()
            print(f"Cleaned up spec draft: {spec_path.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
