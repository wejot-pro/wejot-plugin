#!/usr/bin/env python3
"""批量生成问卷 JSON + full HTML（含 GENERIC）。

# TEMPLATE_I18N_SHELL_V2  # E2B 模板构建签名标记（壳 locale 修复），勿删

Templates and defaults are resolved from this skill package by `utils.skill_paths`.

HTML：若输出目录已有 `survey-unified-generate.html`，则在其上**仅刷新**问卷标题/描述、
optionValue 常量脚本（BODY 内锚点区间）、以及 QUESTION_LIST_START～QUESTION_INSERT_POINT
之间的题目 DOM；其余 DOM/脚本/样式保留。若该文件不存在，则从 `survey-unified-sample.html`
整页模板生成（与历史行为一致）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import uuid
from dataclasses import dataclass
from utils.checkbox_choices import checkbox_option_count, normalize_checkbox_choices
from survey_ui_i18n import (
    html_dict_for_locale,
    inject_survey_ui_i18n,
    load_locale_dict_file,
    localized_default_scale_options,
    other_labels_for_locale,
    warn_if_custom_locale_needed,
)
from html import escape as html_escape
from pathlib import Path
from typing import Any
from utils.skill_paths import (
    LEGACY_SYSTEM_JSON_TEMPLATE_PATH,
    MINIMAL_SPEC_EXAMPLE_PATH,
    MINIMAL_SPEC_TEMPLATE_PATH,
    OUTPUT_CSS_NAME,
    OUTPUT_HTML_NAME,
    OUTPUT_JSON_NAME,
    SYSTEM_HTML_TEMPLATE_PATH,
    SYSTEM_QUESTION_DEFAULTS_PATH,
    SYSTEM_QUESTIONARE_TEMPLATES_DIR,
    SYSTEM_SURVEY_UI_CSS_PATH,
    SYSTEM_SURVEY_UI_JS_PATH,
    resolve_work_dir,
)

# Backward-compatible constant for scripts importing this name.
SYSTEM_JSON_TEMPLATE_PATH = SYSTEM_QUESTION_DEFAULTS_PATH

TYPE_TO_NUM = {
    "RADIO": "8",
    "CHECKBOX": "9",
    "TEXTAREA": "1",
    "UPLOAD": "15",
    "SCALE": "10",
    "MATRIX_SCALE": "28",
    "GENERIC": "39",
}
TYPE_ALIASES = {
    "INPUT": "TEXTAREA",
}

COMMON_QUESTION_FIELDS = {
    "title",
    "type",
    "required",
    "page",
    "code",
    "description",
    "uuid",
}
TYPE_SPEC_FIELDS = {
    "RADIO": {"options", "otherOption"},
    "CHECKBOX": {"options", "minChoices", "maxChoices", "otherOption"},
    "TEXTAREA": {"placeholder", "minLength", "maxLength"},
    "UPLOAD": {"maxFileCount", "maxFileSize", "fileTypes"},
    "SCALE": {"scaleOptions", "scaleLabels"},
    "MATRIX_SCALE": {"rows", "matrixColumns", "dynamicRows"},
    "GENERIC": {"answerKeys", "userAnswersSample", "chartHtml", "genericStyle", "genericHtml", "genericScript"},
}

# 允许上传的文件扩展名白名单（小写、无点），即写入 fileTypes 的规范格式。
# ⚠️ 须与 Java UploadSurveyQuestionHandler.allowedExtensions 保持一致，否则上传题会入库失败。
ALLOWED_FILE_EXTENSIONS = [
    # 图片
    "jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "heic", "tiff",
    # 文档
    "pdf", "doc", "docx", "xls", "xlsx", "csv", "ppt", "pptx", "txt", "rtf", "md",
    # 压缩包
    "zip", "rar", "7z", "gz", "tar",
    # 音频
    "mp3", "wav", "m4a", "aac", "ogg", "flac",
    # 视频
    "mp4", "mov", "avi", "mkv", "webm", "wmv", "flv",
]
_ALLOWED_FILE_EXTENSIONS_SET = set(ALLOWED_FILE_EXTENSIONS)
# MIME 通配 → 扩展名集合
_MIME_WILDCARD_MAP = {
    "image/*": ["jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "heic", "tiff"],
    "audio/*": ["mp3", "wav", "m4a", "aac", "ogg", "flac"],
    "video/*": ["mp4", "mov", "avi", "mkv", "webm", "wmv", "flv"],
}
# 常见完整 MIME → 扩展名
_MIME_TO_EXT = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "text/plain": "txt",
    "text/csv": "csv",
    "application/zip": "zip",
    "application/x-rar-compressed": "rar",
    "application/x-7z-compressed": "7z",
}

# 上传题默认值（maxFileSize 字段单位 KB）。
# spec / schema 中若显式指定 maxFileCount / maxFileSize，则以指定值为准；未指定时回退到以下默认值。
MAX_UPLOAD_FILE_COUNT = 1
MAX_UPLOAD_FILE_SIZE_KB = 102400  # 100 MB


def _spec_fix_hint() -> str:
    return (
        "Fix per the spec schema and the example, then retry: "
        f"schema={MINIMAL_SPEC_TEMPLATE_PATH}, example={MINIMAL_SPEC_EXAMPLE_PATH}；"
        "The top level must be survey + questions; questions go in the questions array."
    )


def _raise_spec_error(msg: str) -> None:
    raise ValueError(f"{msg}\n{_spec_fix_hint()}")


def validate_spec_chart_html(spec: dict[str, Any]) -> None:
    """校验 GENERIC chartHtml；报错定位优先 uuid，否则 code。"""
    from utils.chart_html_syntax import validate_spec_questions_chart_html

    errors = validate_spec_questions_chart_html(spec.get("questions") or [])
    if errors:
        detail = "\n".join(f"- {e}" for e in errors)
        _raise_spec_error(f"GENERIC chartHtml syntax validation failed in the spec:\n{detail}")


def validate_spec_structure(spec: Any, *, require_survey: bool) -> None:
    if not isinstance(spec, dict):
        _raise_spec_error("The spec top level must be an object.")
    allowed_top = {"questions"} | ({"survey"} if require_survey else set())
    unknown_top = sorted(set(spec.keys()) - allowed_top)
    if unknown_top:
        _raise_spec_error(f"The spec top level has undefined fields: {unknown_top}")
    if require_survey:
        survey = spec.get("survey")
        if not isinstance(survey, dict):
            _raise_spec_error("The survey object is missing.")
        survey_unknown = sorted(set(survey.keys()) - {"title", "description"})
        if survey_unknown:
            _raise_spec_error(f"The survey object has undefined fields: {survey_unknown}")
        if not str(survey.get("title", "")).strip():
            _raise_spec_error("survey.title cannot be empty.")
        if not isinstance(survey.get("description", ""), str):
            _raise_spec_error("survey.description must be a string.")
    questions = spec.get("questions")
    if not isinstance(questions, list):
        _raise_spec_error("questions must be an array.")
    if len(questions) == 0:
        return
    for idx, q in enumerate(questions, start=1):
        if not isinstance(q, dict):
            _raise_spec_error(f"questions[{idx}] must be an object.")
        qtype = TYPE_ALIASES.get(str(q.get("type", "")).upper(), str(q.get("type", "")).upper())
        if qtype not in TYPE_TO_NUM:
            _raise_spec_error(f"questions[{idx}] type is unsupported or missing: {q.get('type')!r}")
        unknown_fields = sorted(set(q.keys()) - COMMON_QUESTION_FIELDS - TYPE_SPEC_FIELDS[qtype])
        if unknown_fields:
            _raise_spec_error(f"questions[{idx}]({qtype}) has undefined fields: {unknown_fields}")
        if not str(q.get("title", "")).strip():
            _raise_spec_error(f"questions[{idx}] title cannot be empty.")
        if qtype in {"RADIO", "CHECKBOX"}:
            options = q.get("options")
            if not isinstance(options, list) or len(options) == 0:
                _raise_spec_error(f"questions[{idx}]({qtype}) options must be a non-empty array.")
            for option_index, option in enumerate(options, start=1):
                if isinstance(option, str) and option.strip():
                    continue
                if isinstance(option, dict) and str(option.get("label", "")).strip():
                    continue
                _raise_spec_error(
                    f"questions[{idx}]({qtype}) options[{option_index}] must be a non-empty string or an object with a label."
                )
        if qtype == "MATRIX_SCALE":
            rows = q.get("rows")
            if not isinstance(rows, list):
                _raise_spec_error(f"questions[{idx}](MATRIX_SCALE) rows must be an array.")
            dynamic_rows = q.get("dynamicRows", False)
            if not isinstance(dynamic_rows, bool):
                _raise_spec_error(
                    f"questions[{idx}](MATRIX_SCALE) dynamicRows must be a boolean."
                )
            if not rows:
                if dynamic_rows:
                    _raise_spec_error(
                        f"questions[{idx}](MATRIX_SCALE) with dynamicRows=true, rows must declare a non-empty complete catalog."
                    )
                _raise_spec_error(
                    f"questions[{idx}](MATRIX_SCALE) rows must be a non-empty array."
                )


def gen_uuid() -> str:
    return uuid.uuid4().hex


def normalize_uid(raw_uid: Any) -> str:
    """规整题目 UUID 为校验器要求的 32 位无连字符小写 hex。

    校验器 _looks_like_uuid 要求 ^[0-9a-f]{32}$；LLM 写的 spec 里 uuid 经常是
    题目 code 或带连字符的标准 UUID，直接透传会导致 HTML 过不了 UUID 校验、
    触发模型反复手改。这里统一规整：
    - 已是 32-hex：原样；带连字符的标准 UUID：去连字符保留同一标识；
    - 其余（code/空/非法）：重新生成。
    """
    s = str(raw_uid or "").strip().replace("-", "").lower()
    return s if re.fullmatch(r"[0-9a-f]{32}", s) else gen_uuid()


def normalize_code(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or f"q_{gen_uuid()[:8]}"


def _format_data_scale_value(score: Any) -> str:
    """与 HTML data-scale-value 一致：整数不保留 .0。"""
    if isinstance(score, bool):
        return str(score)
    if isinstance(score, int) and not isinstance(score, bool):
        return str(score)
    if isinstance(score, float):
        if score == int(score):
            return str(int(score))
        return str(score).rstrip("0").rstrip(".") if "." in str(score) else str(score)
    s = str(score).strip()
    return s


def normalize_file_types(raw: Any) -> list[str]:
    """将 spec 的 fileTypes 归一化为 Java 可入库的「小写、无点扩展名」白名单子集。

    兼容 AI 可能写出的多种格式：
    - 带点 ".pdf" / 大写 "PDF" → "pdf"
    - MIME 通配 "image/*" / "audio/*" / "video/*" → 展开为对应扩展名
    - 常见完整 MIME "application/pdf" / "image/png" → "pdf" / "png"
    白名单外的项直接丢弃；全部不合法或非列表时返回 []（调用方回退默认值）。
    """
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        token = item.strip().lower()
        if not token:
            continue
        if token in _MIME_WILDCARD_MAP:
            candidates = _MIME_WILDCARD_MAP[token]
        elif token in _MIME_TO_EXT:
            candidates = [_MIME_TO_EXT[token]]
        else:
            ext = token.lstrip(".")
            if "/" in ext:  # 形如 "image/png" 取子类型
                ext = ext.split("/", 1)[1]
            candidates = [ext]
        for ext in candidates:
            if ext in _ALLOWED_FILE_EXTENSIONS_SET and ext not in result:
                result.append(ext)
    return result


def _normalize_scale_options_list(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        return []
    out: list[dict[str, Any]] = []
    for i, o in enumerate(raw, start=1):
        if not isinstance(o, dict):
            raise ValueError("Every item in scaleOptions/matrixColumns must be an object with title and score; sort optional")
        # 兼容矩阵列约定字段 columnTitle（schema anyOf 允许 columnTitle/title）：
        # 否则 columnTitle 会被丢弃，导致刻度格文本与后端 columnTitle 双双为空（空格子）。
        title = o.get("title", "")
        if not str(title).strip():
            title = o.get("columnTitle", "") or o.get("label", "")
        score = o.get("score", i)
        if not isinstance(score, (int, float, str)):
            raise ValueError(f"score in scaleOptions must be a number: {o!r}")
        try:
            score_f = float(str(score)) if isinstance(score, str) else float(score)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Cannot parse scale score: {o!r}") from e
        sort_v = o.get("sort", i)
        if not isinstance(sort_v, (int, float)):
            sort_v = i
        out.append(
            {
                "sort": int(sort_v) if not isinstance(sort_v, bool) else i,
                "score": score_f,
                "title": str(title),
            }
        )
    out.sort(key=lambda x: (x["sort"], x.get("score", 0)))
    return out


def _normalize_matrix_rows(raw: Any, q_title: str = "") -> list[str]:
    """矩阵量表题的行（维度）规整：统一抽取为非空字符串列表。

    兼容三种来源：纯字符串、{"rowTitle": ...}、{"title": ...}/{"label": ...}。
    任一行标题为空/缺失即报错——空行标题会让后端
    t_survey_question_matrix_scale_row.title 插入 NULL，导致整卷入库失败（500），
    前端预览区永久 loading。
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"MATRIX_SCALE rows must be an array: {q_title!r}")
    out: list[str] = []
    for i, r in enumerate(raw, start=1):
        if isinstance(r, dict):
            text = r.get("rowTitle") or r.get("title") or r.get("label") or ""
        else:
            text = r
        text = str(text).strip()
        if not text:
            raise ValueError(f"MATRIX_SCALE row {i} has an empty title: {q_title!r} (row titles must not be empty)")
        out.append(text)
    return out

def option_label(option: Any) -> str:
    """Return the display label for compact strings and canonical catalog objects."""
    if isinstance(option, dict):
        return str(option.get("label", "")).strip()
    return str(option or "").strip()


def stable_option_value(question_code: str, sort: int, label: str) -> str:
    """与 HTML data-option-value 一致、可复现的稳定取值（不依赖随机 uuid）。"""
    # 手动处理 normalize，避免 normalize_code 的随机 UUID
    text = option_label(label).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    slug = re.sub(r"_+", "_", text).strip("_")

    if not slug:
        h = hashlib.md5(option_label(label).encode("utf-8")).hexdigest()[:10]
        slug = f"h_{h}"
    raw = f"{question_code}__{sort}__{slug}"
    return re.sub(r"_+", "_", raw).strip("_")[:120]


@dataclass
class QuestionSpec:
    title: str
    qtype: str
    required: int
    page: int
    code: str
    sort: int
    description: str = ""
    uid: str = ""
    options: list[str] | None = None
    scale_options: list[dict[str, Any]] | None = None
    scale_labels: dict[str, str] | None = None
    matrix_rows: list[str] | None = None
    matrix_columns: list[dict[str, Any]] | None = None
    dynamic_rows: bool = False
    max_choices: int | None = None
    min_choices: int | None = None
    other_option: bool = False
    placeholder: str = "Please enter..."
    min_length: int = 0
    max_length: int = 255
    max_file_count: int = 1
    max_file_size: int = MAX_UPLOAD_FILE_SIZE_KB
    file_types: list[str] | None = None
    answer_keys: list[str] | None = None
    user_answers_sample: list[dict[str, Any]] | None = None
    chart_html: str | None = None
    generic_style: str = "/* custom question style content */"
    generic_html: str = "<!-- custom question html structure -->"
    generic_script: str = "/* ========== custom question submit script (AI writes here) ========== */"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_system_json_template() -> dict[str, Any]:
    """加载生成脚本默认值；兼容旧沙箱中尚未同步的 question_schema.json。"""
    for path in (SYSTEM_QUESTION_DEFAULTS_PATH, LEGACY_SYSTEM_JSON_TEMPLATE_PATH):
        if path.is_file():
            data = load_json(path)
            if isinstance(data, dict):
                return data
    return {}


def parse_questions(spec: dict[str, Any], *, locale: str | None = None) -> list[QuestionSpec]:
    out: list[QuestionSpec] = []
    default_placeholder = html_dict_for_locale(locale)["placeholder"]
    for idx, raw in enumerate(spec.get("questions", []), start=1):
        qtype = TYPE_ALIASES.get(str(raw["type"]).upper(), str(raw["type"]).upper())
        if qtype not in TYPE_TO_NUM:
            raise ValueError(f"Unsupported question type: {qtype}")
        scale_opts: list[dict[str, Any]] | None = None
        matrix_cols: list[dict[str, Any]] | None = None
        matrix_rows: list[str] | None = None
        scale_labels: dict[str, str] | None = None
        if qtype == "SCALE":
            so = raw.get("scaleOptions")
            if so is not None:
                scale_opts = _normalize_scale_options_list(so)
                if not scale_opts:
                    raise ValueError("SCALE: when scaleOptions is provided, the list must not be empty")
            elif raw.get("minScale") is not None and raw.get("maxScale") is not None:
                min_s = int(raw["minScale"])
                max_s = int(raw["maxScale"])
                scale_opts = [{"title": str(i), "score": i, "sort": j + 1} for j, i in enumerate(range(min_s, max_s + 1))]
            if raw.get("scaleLabels"):
                scale_labels = {
                    "left": raw["scaleLabels"].get("left", ""),
                    "right": raw["scaleLabels"].get("right", ""),
                }
        if qtype == "MATRIX_SCALE":
            mc = raw.get("matrixColumns")
            if mc is not None:
                matrix_cols = _normalize_scale_options_list(mc)
                if not matrix_cols:
                    raise ValueError("MATRIX_SCALE: when matrixColumns is provided, the list must not be empty")
            matrix_rows = _normalize_matrix_rows(raw.get("rows"), raw.get("title", ""))
        min_choices_val: int | None = None
        max_choices_val: int | None = None
        if qtype == "CHECKBOX":
            other_opt = bool(raw.get("otherOption", False))
            opt_count = checkbox_option_count(raw.get("options"), other_option=other_opt)
            min_choices_val, max_choices_val = normalize_checkbox_choices(
                raw.get("minChoices"), raw.get("maxChoices"), option_count=opt_count
            )
        out.append(
            QuestionSpec(
                title=raw["title"],
                qtype=qtype,
                required=1 if raw.get("required", False) else 0,
                page=int(raw.get("page", 1)),
                code=raw.get("code") or normalize_code(raw["title"]),
                sort=idx * 1000,
                description=raw.get("description", ""),
                uid=normalize_uid(raw.get("uuid")),
                options=raw.get("options"),
                scale_options=scale_opts,
                scale_labels=scale_labels,
                matrix_rows=matrix_rows,
                matrix_columns=matrix_cols,
                dynamic_rows=bool(raw.get("dynamicRows", False)),
                max_choices=max_choices_val,
                min_choices=min_choices_val,
                other_option=bool(raw.get("otherOption", False)),
                placeholder=raw.get("placeholder", default_placeholder),
                min_length=int(raw.get("minLength", 0)),
                max_length=int(raw.get("maxLength", 255)),
                max_file_count=int(raw["maxFileCount"]) if raw.get("maxFileCount") is not None else MAX_UPLOAD_FILE_COUNT,
                max_file_size=int(raw["maxFileSize"]) if raw.get("maxFileSize") is not None else MAX_UPLOAD_FILE_SIZE_KB,
                file_types=normalize_file_types(raw.get("fileTypes")) or None,
                answer_keys=raw.get("answerKeys"),
                user_answers_sample=raw.get("userAnswersSample"),
                chart_html=raw.get("chartHtml"),
                generic_style=raw.get("genericStyle", "/* custom question style content */"),
                generic_html=raw.get("genericHtml", "<!-- custom question html structure -->"),
                generic_script=raw.get(
                    "genericScript",
                    "/* ========== custom question submit script (AI writes here) ========== */",
                ),
            )
        )

    # 验证页面顺序：questions 数组必须按实际问卷页面和位置排列
    # 若出现 page 1, 2, 1 这类乱序，会导致 DOM 结构错误（page=1 题目渲染到后续页面）
    max_page_seen = 0
    for q in out:
        if q.page < max_page_seen:
            raise ValueError(
                f"questions array page-order anomaly: question \"{q.title}\" has page={q.page} less than the previous page={max_page_seen}."
                "questions must follow the actual survey pages and positions; same-page questions must be contiguous, "
                "and must not appear out of order like page 1, 2, 1."
            )
        if q.page > max_page_seen:
            max_page_seen = q.page

    return out


def build_schema(
    spec: dict[str, Any],
    tmpl: dict[str, Any],
    questions: list[QuestionSpec],
    *,
    locale: str | None = None,
) -> dict[str, Any]:
    out = {
        "survey": {
            "title": spec["survey"]["title"],
            "description": spec["survey"]["description"],
        },
        "radioQuestions": [],
        "checkboxQuestions": [],
        "textQuestions": [],
        "uploadQuestions": [],
        "scaleQuestions": [],
        "matrixScaleQuestions": [],
        "genericQuestions": [],
    }
    # AI 未指定 fileTypes 时，默认放开全部支持格式（仅当题目明确限定时才在 spec 里收窄）
    default_file_types = list(ALLOWED_FILE_EXTENSIONS)
    other_label = html_dict_for_locale(locale)["other"]
    default_scale_options = (tmpl.get("scaleQuestions", [{}])[0].get("options", []) if tmpl.get("scaleQuestions") else [])
    default_matrix_columns = (
        tmpl.get("matrixScaleQuestions", [{}])[0].get("columns", [])
        if tmpl.get("matrixScaleQuestions")
        else []
    )
    generic_tmpl = tmpl.get("genericQuestions", [{}])[0] if tmpl.get("genericQuestions") else {}

    for q in questions:
        base = {
            "title": q.title,
            "description": q.description,
            "code": q.code,
            "uuid": q.uid,
            "type": q.qtype,
            "required": q.required,
            "sort": q.sort,
        }
        if q.qtype == "RADIO":
            options = [
                {"sort": i + 1, "label": (opt.get("label", "") if isinstance(opt, dict) else opt), "description": ""}
                for i, opt in enumerate(q.options or [])
            ]
            if q.other_option:
                base["otherEnabled"] = 1
                base["otherText"] = other_label
            base["options"] = options
            out["radioQuestions"].append(base)
        elif q.qtype == "CHECKBOX":
            raw_options = q.options or []
            options = [
                {"sort": i + 1, "label": (opt.get("label", "") if isinstance(opt, dict) else opt), "description": ""}
                for i, opt in enumerate(raw_options)
            ]
            if q.other_option:
                base["otherEnabled"] = 1
                base["otherText"] = other_label
            base["options"] = options
            opt_count = checkbox_option_count(raw_options, other_option=q.other_option)
            min_c, max_c = normalize_checkbox_choices(
                q.min_choices, q.max_choices, option_count=opt_count
            )
            base["minChoices"] = min_c
            base["maxChoices"] = max_c
            out["checkboxQuestions"].append(base)
        elif q.qtype == "TEXTAREA":
            base["placeholder"] = q.placeholder
            base["defaultValue"] = ""
            base["minLength"] = q.min_length
            base["maxLength"] = q.max_length
            out["textQuestions"].append(base)
        elif q.qtype == "UPLOAD":
            base["maxFileCount"] = q.max_file_count
            base["maxFileSize"] = q.max_file_size
            base["fileTypes"] = q.file_types or default_file_types
            out["uploadQuestions"].append(base)
        elif q.qtype == "SCALE":
            if q.scale_options:
                base["options"] = [
                    {"sort": int(o.get("sort", i + 1)), "score": float(o["score"]), "title": str(o["title"])}
                    for i, o in enumerate(q.scale_options)
                ]
            else:
                base["options"] = [
                    dict(x) for x in (localized_default_scale_options(locale) or default_scale_options or [])
                ]
            if q.scale_labels:
                base["scaleLabels"] = q.scale_labels
            out["scaleQuestions"].append(base)
        elif q.qtype == "MATRIX_SCALE":
            # 输出字段与后端 DTO 对齐：列标题 columnTitle、行标题 rowTitle（与数字分值 score 分离）。
            # 兼容来源对象用 title 的情况（输入授权格式 matrixColumns/模板默认列仍用 title）。
            # 行（rows）已在 parse_questions 经 _normalize_matrix_rows 规整为非空字符串。
            src_cols = (
                q.matrix_columns
                if q.matrix_columns
                else (localized_default_scale_options(locale, matrix=True) or default_matrix_columns or [])
            )
            base["columns"] = [
                {
                    "sort": int(c.get("sort", i + 1)),
                    "score": float(c["score"]),
                    "columnTitle": str(c.get("columnTitle", c.get("title", ""))),
                }
                for i, c in enumerate(src_cols)
            ]
            base["rows"] = [
                {
                    "rowTitle": r,
                    "sort": i + 1,
                }
                for i, r in enumerate(q.matrix_rows or [])
            ]
            base["dynamicRows"] = bool(q.dynamic_rows)
            out["matrixScaleQuestions"].append(base)
        elif q.qtype == "GENERIC":
            base["answerKeys"] = q.answer_keys or generic_tmpl.get("answerKeys", ["value"])
            base["userAnswersSample"] = (
                q.user_answers_sample if q.user_answers_sample is not None else generic_tmpl.get("userAnswersSample", [])
            )
            base["chartHtml"] = q.chart_html or generic_tmpl.get("chartHtml", "")
            base["genericStyle"] = q.generic_style
            base["genericHtml"] = q.generic_html
            base["genericScript"] = q.generic_script
            out["genericQuestions"].append(base)
    return out


def generate_option_value_constants(
    questions: list[QuestionSpec], *, locale: str | None = None
) -> str:
    """生成 optionValue 常量定义 + UUID 解析器，供 survey-ui.js 使用"""
    lines = ["// Auto-generated constants for survey logic"]
    lines.append("// DO NOT EDIT - regenerated each time survey is rebuilt")
    lines.append("")
    lines.append("function resolveUuidByIndex(indexNum) {")
    lines.append("  const item = document.querySelector('.q[data-question][data-question-index=\"' + indexNum + '\"]');")
    lines.append("  return item ? item.getAttribute('data-question-uuid') : null;")
    lines.append("}")
    lines.append("")
    lines.append("function getScaleScore(questionUuid) {")
    lines.append("  const ans = window.SurveyDataBridge && window.SurveyDataBridge.getAnswer ? window.SurveyDataBridge.getAnswer(questionUuid) : null;")
    lines.append("  return ans && ans.scaleValue !== undefined ? ans.scaleValue : null;")
    lines.append("}")
    lines.append("")
    lines.append("function getMatrixScore(questionUuid, rowTitle) {")
    lines.append("  const ans = window.SurveyDataBridge && window.SurveyDataBridge.getAnswer ? window.SurveyDataBridge.getAnswer(questionUuid) : null;")
    lines.append("  if (!ans || !Array.isArray(ans.value)) return null;")
    lines.append("  const row = ans.value.find(row => row && row.rowTitle === rowTitle);")
    lines.append("  return row && Number.isFinite(Number(row.score)) ? Number(row.score) : null;")
    lines.append("}")
    lines.append("")

    for q in questions:
        q_num = q.sort // 1000
        lines.append(f"// Q{q_num}: {q.title}")
        lines.append(f"const Q{q_num}_UUID = resolveUuidByIndex({q_num}); // {q.uid}")
        if q.qtype in ("RADIO", "CHECKBOX"):
            for i, opt in enumerate(q.options or [], start=1):
                ov = stable_option_value(q.code, i, opt)
                const_name = f"Q{q_num}_OPT_{i}"
                lines.append(f"const {const_name} = '{ov}'; // {option_label(opt)}")
            if q.other_option:
                other_value = f"{q.code}__other__other"
                lines.append(
                    f"const Q{q_num}_OTHER_OPTION_VALUE = "
                    f"{json.dumps(other_value, ensure_ascii=False)}; // other"
                )
        elif q.qtype == "SCALE":
            scale_opts = q.scale_options
            if scale_opts:
                scores = [opt.get("score", i) for i, opt in enumerate(scale_opts, start=1)]
                min_score = min(scores)
                max_score = max(scores)
                lines.append(f"// Rating question: read the numeric score with getScaleScore(Q{q_num}_UUID) or SurveyDataBridge.getAnswer(Q{q_num}_UUID).value ({min_score}~{max_score}); don't use .optionValue")
                lines.append(f"const Q{q_num}_SCALE_MIN = {min_score};")
                lines.append(f"const Q{q_num}_SCALE_MAX = {max_score};")
            else:
                lines.append(f"// Rating question: read the numeric score with getScaleScore(Q{q_num}_UUID) or SurveyDataBridge.getAnswer(Q{q_num}_UUID).value; don't use .optionValue")
        elif q.qtype == "MATRIX_SCALE":
            # 维度（行）常量
            for i, row in enumerate(q.matrix_rows or [], start=1):
                const_name = f"Q{q_num}_ROW_{i}"
                row_value = stable_option_value(q.code, i, row)
                # json.dumps 生成 JS 安全的字符串字面量（转义引号/反斜杠）
                lines.append(f"const {const_name} = {json.dumps(row, ensure_ascii=False)}; // 维度{i}")
                lines.append(
                    f"const {const_name}_VALUE = "
                    f"{json.dumps(row_value, ensure_ascii=False)}; // 维度{i}稳定值"
                )
            # 刻度（列）常量
            matrix_cols = q.matrix_columns
            if not matrix_cols:
                matrix_cols = [
                    {"title": t, "score": i + 1}
                    for i, t in enumerate(html_dict_for_locale(locale)["scaleMatrix"])
                ]
            for i, col in enumerate(matrix_cols, start=1):
                score = col.get("score", i)
                title = col.get("title", "")
                const_name = f"Q{q_num}_OPT_{i}"
                lines.append(f"const {const_name} = {score}; // {title}")
        lines.append("")

    return "\n".join(lines)


def _effective_scale_options(
    q: QuestionSpec,
    default_options: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if q.scale_options:
        return q.scale_options
    if default_options:
        return [dict(x) for x in default_options]
    return []


def _effective_matrix_columns(
    q: QuestionSpec,
    default_columns: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if q.matrix_columns:
        return q.matrix_columns
    if default_columns:
        return [dict(x) for x in default_columns]
    return []


def build_question_html(
    q: QuestionSpec,
    idx: int,
    *,
    default_scale_options: list[dict[str, Any]] | None = None,
    default_matrix_columns: list[dict[str, Any]] | None = None,
    locale: str | None = None,
) -> str:
    type_num = TYPE_TO_NUM[q.qtype]
    req_str = "true" if q.required else "false"
    q_num = f"{idx:02d}"
    # SCALE / MATRIX_SCALE 的动态选项在各自分支内生成，此处不再需要固定字符串
    ui = html_dict_for_locale(locale)

    def build_question_shell(body: str) -> str:
        req_span = '<span class="req">*</span>' if q.required else ''
        desc_html = f'            <div class="qd">{html_escape(q.description, quote=False)}</div>\n' if q.description else ''
        extra_attrs = ""
        if q.qtype == "CHECKBOX":
            opt_count = checkbox_option_count(q.options, other_option=q.other_option)
            min_c, max_c = normalize_checkbox_choices(
                q.min_choices, q.max_choices, option_count=opt_count
            )
            extra_attrs += f' data-min-choices="{min_c}" data-max-choices="{max_c}"'
        elif q.qtype == "UPLOAD":
            mfc = q.max_file_count if q.max_file_count is not None else 1
            mfs = q.max_file_size if q.max_file_size is not None else MAX_UPLOAD_FILE_SIZE_KB
            fts = ",".join(q.file_types or [])
            extra_attrs += f' data-max-file-count="{mfc}" data-max-file-size="{mfs}"'
            if fts:
                extra_attrs += f' data-file-types="{html_escape(fts, quote=True)}"'
        elif q.qtype == "MATRIX_SCALE" and q.dynamic_rows:
            extra_attrs += ' data-dynamic-rows="true"'
        return f"""<!-- QUESTION_REGION_START: index={idx} type={type_num}({q.qtype}) title="{q.title}" page={q.page} -->
    <div class="q" data-question data-question-uuid="{q.uid}" data-question-type="{type_num}" data-question-index="{idx}" data-code="{q.code}" data-page="{q.page}" data-required="{req_str}"{extra_attrs}>
        <div class="qh">
            {req_span}
            <span data-q-number>{q_num}</span>
            <span data-title>{q.title}</span>
{desc_html}        </div>
{body}    </div>
    <!-- QUESTION_REGION_END: index={idx} -->
"""

    def build_choice_option(option_kind: str, option_value: str, label: Any, *, is_other: bool = False) -> str:
        label = option_label(label)
        input_type = 'radio' if option_kind == 'radio' else 'checkbox'
        control_class = 'rd' if option_kind == 'radio' else 'cb'
        # 勾选标记由 CSS 伪元素渲染，不作为文本节点（避免污染选项纯文本取数）
        control_inner = ''
        other_attr = ' data-option-other' if is_other else ''
        other_input = (
            f'<input type="text" class="oi" placeholder="{ui["placeholder"]}" data-other-input />'
            if is_other else ''
        )
        return (
            f'<label class="opt" data-option data-option-value="{html_escape(option_value, quote=True)}"{other_attr}>'
            f'<input type="{input_type}" name="{q.code}" value="{html_escape(option_value, quote=True)}" />'
            f'<span class="{control_class}">{control_inner}</span>'
            f'<span>{html_escape(label, quote=False)}</span>'
            f'{other_input}</label>'
        )

    body = ""
    if q.qtype == "RADIO":
        parts: list[str] = []
        for i, o in enumerate(q.options or [], start=1):
            ov = stable_option_value(q.code, i, o)
            parts.append(build_choice_option("radio", ov, o))
        if q.other_option:
            other_value = f"{q.code}__other__other"
            parts.append(build_choice_option("radio", other_value, ui["other"], is_other=True))
        options = "\n            ".join(parts)
        body = f'        <div class="qb">\n            {options}\n        </div>\n'
    elif q.qtype == "CHECKBOX":
        parts = []
        for i, o in enumerate(q.options or [], start=1):
            ov = stable_option_value(q.code, i, o)
            parts.append(build_choice_option("checkbox", ov, o))
        if q.other_option:
            other_value = f"{q.code}__other__other"
            parts.append(build_choice_option("checkbox", other_value, ui["other"], is_other=True))
        options = "\n            ".join(parts)
        body = f'        <div class="qb">\n            {options}\n        </div>\n'
    elif q.qtype == "TEXTAREA":
        body = f'        <div class="qb">\n            <textarea placeholder="{q.placeholder}" data-input-type="text" data-max-length="{q.max_length}" data-min-length="{q.min_length}"></textarea>\n        </div>\n'
    elif q.qtype == "UPLOAD":
        # fileTypes 内部为无点扩展名（给 Java 入库）；HTML accept 需带点的 Web 形式。
        accept_value = ",".join("." + e for e in (q.file_types or []))
        accept_attr = f' accept="{accept_value}"' if accept_value else ''
        body = f'        <div class="qb">\n            <label class="up">\n                <input type="file"{accept_attr} />\n                <span class="up-icon"></span>\n                <span>{ui["upload"]}</span>\n            </label>\n        </div>\n'
    elif q.qtype == "SCALE":
        scale_opts = _effective_scale_options(q, default_scale_options)
        if scale_opts:
            labels = [o["title"] for o in scale_opts]
            sc_items = "".join(
                f'<div class="sc" data-option data-scale-value="{_format_data_scale_value(o["score"])}">{html_escape(str(o["title"]), quote=False)}</div>'
                for o in scale_opts
            )
        else:
            labels = q.options or ui["scaleSatisfaction"]
            sc_items = "".join(f'<div class="sc" data-option data-scale-value="{i+1}">{i+1}</div>' for i in range(len(labels)))
        left_label = q.scale_labels.get("left", labels[0]) if q.scale_labels else labels[0]
        right_label = q.scale_labels.get("right", labels[-1]) if q.scale_labels else labels[-1]
        sl_html = f'            <div class="sl"><span>{left_label}</span><span>{right_label}</span></div>\n' if (left_label or right_label) else ''
        body = f'        {sl_html}        <div class="qb">\n            <div class="sv" data-survey-role="scale-group">{sc_items}</div>\n        </div>\n'
    elif q.qtype == "MATRIX_SCALE":
        matrix_cols = _effective_matrix_columns(q, default_matrix_columns)
        if matrix_cols:
            labels = [c.get("title") or c.get("columnTitle") or "" for c in matrix_cols]
            header_items = "".join(
                f'<div class="mc matrix-column" data-matrix-column data-scale-value="{_format_data_scale_value(c["score"])}"><span class="matrix-column-text">{html_escape(str(c.get("title") or c.get("columnTitle") or ""), quote=False)}</span></div>'
                for c in matrix_cols
            )
            sc_items = "".join(
                f'<div class="sc" data-option data-scale-value="{_format_data_scale_value(c["score"])}"></div>'
                for c in matrix_cols
            )
        else:
            labels = q.options or ui["scaleMatrix"]
            header_items = "".join(
                f'<div class="mc matrix-column" data-matrix-column data-scale-value="{i+1}"><span class="matrix-column-text">{html_escape(str(label), quote=False)}</span></div>'
                for i, label in enumerate(labels)
            )
            sc_items = "".join(f'<div class="sc" data-option data-scale-value="{i+1}"></div>' for i in range(len(labels)))

        def build_matrix_row(row_label: str, row_index: int) -> str:
            escaped_attr = html_escape(row_label, quote=True)
            escaped_value = html_escape(
                stable_option_value(q.code, row_index, row_label), quote=True
            )
            return (
                f'<div class="mr" data-survey-role="matrix-row" data-matrix-row="{escaped_attr}" '
                f'data-matrix-row-label="{escaped_attr}" data-matrix-row-value="{escaped_value}">'
                f'<span class="matrix-row-title">{html_escape(row_label, quote=False)}</span>'
                f'<div class="mv" data-survey-role="matrix-values">{sc_items}</div></div>'
            )

        rows = "\n            ".join(
            build_matrix_row(r, i) for i, r in enumerate(q.matrix_rows or [], start=1)
        )
        header_html = f'<div class="mh" data-survey-role="matrix-header"><span class="matrix-corner" aria-hidden="true"></span>{header_items}</div>'
        body = f'        <div class="qb">\n            <div class="matrix-shell" data-survey-role="matrix-group" style="--matrix-col-count:{len(labels) if labels else 1}">\n                <div class="matrix-header-scroll" data-survey-role="matrix-header-scroll">\n                    {header_html}\n                </div>\n                <div class="mx matrix-body-scroll" data-survey-role="matrix-scroll">\n                    <div class="matrix-body" data-survey-role="matrix-body">\n            {rows}\n                    </div>\n                </div>\n            </div>\n        </div>\n'
    elif q.qtype == "GENERIC":
        answer_keys = ",".join(q.answer_keys or ["value"])
        body = f"""        <div class="qb">
            <div class="gx" data-survey-role="generic-container" data-question-uuid="{q.uid}">
                <style>
{q.generic_style}
                </style>
                <div class="gc">
{q.generic_html}
                </div>
                <script data-answer-keys="{answer_keys}">
                    (function () {{
                        var scriptEl = document.currentScript;
                        var wrapper = scriptEl && scriptEl.closest('[data-survey-role="generic-container"]');
                        var questionId = wrapper ? wrapper.getAttribute('data-question-uuid') : null;
                        function submitAnswer(answers) {{
                            if (!answers || typeof answers !== 'object' || !questionId) return;
                            if (typeof window.submitGenericAnswer !== 'undefined') window.submitGenericAnswer(questionId, answers);
                        }}
                        function getCurrentAnswer() {{
                            var content = wrapper ? wrapper.querySelector('.gc') : null;
                            if (!content) return {{}};
                            var compEl = content.querySelector('[id]');
                            if (compEl && compEl._surveyComponent && typeof compEl._surveyComponent.getValue === 'function') {{
                                var result = compEl._surveyComponent.getValue();
                                if (result && result.values) return result.values;
                            }}
                            return {{}};
                        }}
                        if (questionId && wrapper) {{
                            window.addEventListener('survey:before-submit', function () {{
                                var ans = getCurrentAnswer();
                                if (ans && typeof ans === 'object' && Object.keys(ans).length > 0) submitAnswer(ans);
                            }});
                        }}
                        try {{
{q.generic_script}
                        }} catch (e) {{
                            console.error('自定义题型脚本执行错误:', questionId, e);
                        }}
                    }})();
                </script>
            </div>
        </div>
"""
    return build_question_shell(body)


def _apply_survey_titles(html: str, spec: dict[str, Any], *, locale: str | None = None) -> str:
    title = spec["survey"]["title"]
    desc = spec["survey"]["description"]
    # New template: <h1 data-title="survey"><span>title</span></h1> and <p data-desc="description"><span>desc</span></p>
    html = re.sub(
        r'(<h1[^>]*data-title="survey"[^>]*>)(.*?)(</h1>)',
        lambda m: m.group(1) + '<span>' + title + '</span>' + m.group(3),
        html,
        count=1,
    )
    html = re.sub(
        r'(<(?:p|div)[^>]*data-desc="description"[^>]*>)(.*?)(</(?:p|div)>)',
        lambda m: m.group(1) + '<span>' + desc + '</span>' + m.group(3),
        html,
        count=1,
    )
    # Also update <title> tag
    html = re.sub(
        r'(<title>)(.*?)(</title>)',
        lambda m: m.group(1) + title + m.group(3),
        html,
        count=1,
    )
    return html


def _option_value_constants_script_tag(js: str) -> str:
    return f"\n    <script>\n{js}\n    </script>\n"


def schema_to_question_specs(schema: dict[str, Any], *, locale: str | None = None) -> list[QuestionSpec]:
    """将 question_schema_generate.json（按题型分桶格式）反序列化为 QuestionSpec 列表。

    典型用途：
    - append_questions_to_survey.py 追加题目后，从合并后的 schema 重建完整 QuestionSpec，
      再调用 generate_option_value_constants 重新生成 survey-ui.js 常量。
    - 任何需要从已有 schema 反推题目结构、再生成前端常量的场景。
    """
    out: list[QuestionSpec] = []
    other_labels = other_labels_for_locale(locale)
    default_placeholder = html_dict_for_locale(locale)["placeholder"]
    bucket_to_type = {
        "radioQuestions": "RADIO",
        "checkboxQuestions": "CHECKBOX",
        "textQuestions": "TEXTAREA",
        "uploadQuestions": "UPLOAD",
        "scaleQuestions": "SCALE",
        "matrixScaleQuestions": "MATRIX_SCALE",
        "genericQuestions": "GENERIC",
    }
    for bucket, qtype in bucket_to_type.items():
        for item in schema.get(bucket, []) or []:
            if not isinstance(item, dict):
                continue
            opts: list[str] | None = None
            scale_opts: list[dict[str, Any]] | None = None
            matrix_rows: list[str] | None = None
            matrix_columns: list[dict[str, Any]] | None = None
            other_option = bool(item.get("otherOption", False)) or int(item.get("otherEnabled", 0) or 0) == 1
            if qtype in ("RADIO", "CHECKBOX"):
                opts = [str((o or {}).get("label", "")) for o in sorted(item.get("options", []), key=lambda x: int((x or {}).get("sort", 0)))]
                if opts and opts[-1] in other_labels:
                    other_option = True
                    opts = opts[:-1]
            if qtype == "SCALE":
                scale_opts = [
                    {"sort": int((o or {}).get("sort", i + 1)), "score": float((o or {}).get("score", i + 1)), "title": str((o or {}).get("title", ""))}
                    for i, o in enumerate(sorted(item.get("options", []), key=lambda x: int((x or {}).get("sort", 0))))
                ]
            if qtype == "MATRIX_SCALE":
                matrix_rows = [
                    str((r or {}).get("rowTitle", (r or {}).get("title", "")))
                    for r in sorted(
                        item.get("rows", []),
                        key=lambda x: int((x or {}).get("sort", 0)),
                    )
                ]
                matrix_columns = [
                    {"sort": int((c or {}).get("sort", i + 1)), "score": float((c or {}).get("score", i + 1)), "title": str((c or {}).get("columnTitle", (c or {}).get("title", "")))}
                    for i, c in enumerate(sorted(item.get("columns", []), key=lambda x: int((x or {}).get("sort", 0))))
                ]
            if qtype == "CHECKBOX":
                opt_count = checkbox_option_count(opts, other_option=other_option)
                min_c, max_c = normalize_checkbox_choices(
                    item.get("minChoices"), item.get("maxChoices"), option_count=opt_count
                )
            else:
                min_c, max_c = None, None
            out.append(
                QuestionSpec(
                    title=str(item.get("title", "")),
                    qtype=qtype,
                    required=1 if bool(item.get("required", 0)) else 0,
                    page=1,
                    code=str(item.get("code", "")),
                    sort=int(item.get("sort", 0)),
                    description=str(item.get("description", "")),
                    uid=str(item.get("uuid", "")),
                    options=opts,
                    scale_options=scale_opts,
                    matrix_rows=matrix_rows,
                    matrix_columns=matrix_columns,
                    dynamic_rows=bool(item.get("dynamicRows", False)),
                    max_choices=max_c,
                    min_choices=min_c,
                    placeholder=str(item.get("placeholder", default_placeholder)),
                    min_length=int(item.get("minLength", 0)),
                    max_length=int(item.get("maxLength", 255)),
                    max_file_count=int(item["maxFileCount"]) if qtype == "UPLOAD" and item.get("maxFileCount") is not None else MAX_UPLOAD_FILE_COUNT,
                    max_file_size=int(item["maxFileSize"]) if qtype == "UPLOAD" and item.get("maxFileSize") is not None else MAX_UPLOAD_FILE_SIZE_KB,
                    file_types=item.get("fileTypes") if qtype == "UPLOAD" else None,
                    answer_keys=item.get("answerKeys") if qtype == "GENERIC" else None,
                    user_answers_sample=item.get("userAnswersSample") if qtype == "GENERIC" else None,
                    chart_html=item.get("chartHtml") if qtype == "GENERIC" else None,
                    other_option=other_option,
                )
            )
    out.sort(key=lambda q: int(q.sort))
    return out


def _ensure_survey_ui_css(output_dir: Path) -> None:
    """若输出目录缺少 survey-ui.css，则从 questionareTemplates 复制（与 JS 同源同落点）。

    已存在则不覆盖，避免冲掉 LLM 已改样式。模板缺失时仅告警，由 validate_standard_survey 拦截。
    """
    css_path = output_dir / OUTPUT_CSS_NAME
    if css_path.is_file():
        return
    template_path = SYSTEM_SURVEY_UI_CSS_PATH
    if not template_path.is_file():
        print(
            f"Warning: {OUTPUT_CSS_NAME} is missing and the template does not exist; write the file manually {css_path}: "
            f"expected_template={template_path} output={css_path}",
            file=sys.stderr,
        )
        return
    shutil.copy2(template_path, css_path)
    print(f"Found a missing css file; copied from the template: {css_path}")


def _marked_line_region(text: str, begin_marker: str, end_marker: str) -> tuple[int, int] | None:
    begin_marker_index = text.find(begin_marker)
    end_marker_index = text.find(end_marker)
    if begin_marker_index < 0 or end_marker_index <= begin_marker_index:
        return None
    begin = text.rfind("\n", 0, begin_marker_index) + 1
    end_break = text.find("\n", end_marker_index)
    end = len(text) if end_break < 0 else end_break + 1
    return begin, end


def _restore_missing_standard_runtime(content: str) -> str:
    """Refresh the shared Runtime while preserving the editable business region."""
    business_region = _marked_line_region(
        content,
        "业务逻辑扩展区 BEGIN",
        "业务逻辑扩展区 END",
    )
    if business_region is None:
        return content
    if not SYSTEM_SURVEY_UI_JS_PATH.is_file():
        raise FileNotFoundError(f"The system survey-ui.js template does not exist: {SYSTEM_SURVEY_UI_JS_PATH}")

    template = SYSTEM_SURVEY_UI_JS_PATH.read_text(encoding="utf-8")
    template_business_region = _marked_line_region(
        template,
        "业务逻辑扩展区 BEGIN",
        "业务逻辑扩展区 END",
    )
    if template_business_region is None:
        raise ValueError("The system survey-ui.js template is missing the business-logic extension area")

    source_begin, source_end = business_region
    template_begin, template_end = template_business_region
    return (
        template[:template_begin]
        + content[source_begin:source_end]
        + template[template_end:]
    )


def _inject_constants_into_survey_ui_js(
    output_dir: Path,
    constants: str,
    locale: str | None = None,
) -> None:
    """将 optionValue 常量字符串注入当前目录 survey-ui.js 顶部，使 LLM 可直接复用 Q1_UUID / Q1_OPT_1 等。

    设计要点：
    - 接受已经生成好的 constants 字符串（而非原始 questions），方便 append_questions_to_survey.py
      等外部脚本直接调用，无需再引入 generate_option_value_constants 的依赖。
    - 通过固定 marker 识别旧常量区，实现幂等注入（多次执行不会重复追加）。
    - locale 仅在新生成（或调用方显式传入）时注入 SURVEY_UI_I18N 文案；None 表示保留文件现有语种，
      避免 append_questions_to_survey.py 追加题目时把已本地化的问卷重置回默认语种。
    """
    js_path = output_dir / "survey-ui.js"
    marker = "// Auto-generated constants for survey logic"

    if js_path.is_file():
        existing = js_path.read_text(encoding="utf-8")
        begin_count = existing.count("// ==================== 业务逻辑扩展区 BEGIN ====================")
        end_count = existing.count("// ==================== 业务逻辑扩展区 END ====================")
        if begin_count > 1 or end_count > 1:
            raise ValueError(
                "survey-ui.js contains duplicate business-logic extension area markers; "
                "keep a single BEGIN/END area before generating"
            )

    if js_path.is_file():
        content = _restore_missing_standard_runtime(
            js_path.read_text(encoding="utf-8")
        )
        # 若已存在旧常量，替换之
        if marker in content:
            # 常量块以 marker 开头，以下一个明确的"文件结构边界"结束：
            # // ===== 注释头、/* 多行注释、(function IIFE、或文件结尾
            # 注意：lookahead 里不能放 \nconst /\nvar /\nlet，因为常量块内部本身就有大量 const 声明
            content = re.sub(
                r"// Auto-generated constants for survey logic[\s\S]*?(?=\n// =====|\n/\* |\n\(function|\Z)",
                constants + "\n",
                content,
                count=1,
            )
        else:
            content = constants + "\n\n" + content
    else:
        template_path = SYSTEM_SURVEY_UI_JS_PATH
        if template_path.is_file():
            content = constants + "\n\n" + template_path.read_text(encoding="utf-8")
        else:
            content = constants

    # 确保业务逻辑扩展区占位符存在（兼容旧对话：模板未更新时自动追加）
    if "// ==================== 业务逻辑扩展区 BEGIN ====================" not in content:
        content = (
            content.rstrip()
            + "\n\n// ===== read-only base ends (SURVEY_UI_INFRA_END) — below is the LLM-editable area =====\n\n"
            + "// ==================== 业务逻辑扩展区 BEGIN ====================\n"
            + "// Mandatory rule: code may only be written between the BEGIN and END markers; inserting anything outside this area is forbidden.\n"
            + "// This area registers business logic with window.SurveyRuntime.registerUserLogic(); the base runs it automatically after initialization.\n"
            + "// Constants: Qn_UUID / Qn_OPT_n / resolveUuidByIndex are injected at the file top; use them directly; duplicate declarations are strictly forbidden.\n"
            + "// Main entry: window.SurveyRuntime.onLogicAnswerChange(detail => { ... })\n"
            + "// Read answers: window.SurveyRuntime.getLogicAnswer(uuid) or window.SurveyDataBridge.getAnswer(uuid)\n"
            + "// Show/hide: window.SurveyRuntime.setLogicQuestionVisibility(uuid, true/false)\n"
            + "// Dynamic items: a standard catalog subset may pass [{value}]; GENERIC or custom copy passes [{value, label, schemaLabel?, source?, meta?}]\n"
            + "// Item exposure: window.SurveyRuntime.getQuestionItemsExposure(uuid)\n"
            + "// Stem copy: window.SurveyRuntime.setQuestionContent(uuid, {title?, description?})\n"
            + "// Oscillation guard: take a signature of the driver answer; return early when the signature is unchanged\n"
            + "// Forbidden: don't cloneNode the .bs / .bp navigation buttons\n"
            + "// Forbidden: don't listen for DOMContentLoaded; the base auto-runs business logic after init\n"
            + "// Same-device breakpoint resume: the base disables it by default (localStorage stores answers + breakpoint page). Set true to enable. Same device only, not cross-device.\n"
            + "\n"
            + "// Same-device breakpoint resume switch (false = off). After restore, must land on the breakpoint page, not restart from the top.\n"
            + "const SURVEY_LOCAL_DRAFT_DEFAULT = true\n"
            + "window.SURVEY_LOCAL_DRAFT_DEFAULT = SURVEY_LOCAL_DRAFT_DEFAULT\n"
            + "\n"
            + "window.SurveyRuntime.registerUserLogic(function() {\n"
            + "  'use strict';\n"
            + "\n"
            + "  // [write business-logic code below this line]\n"
            + "\n"
            + "})\n"
            + "// ==================== 业务逻辑扩展区 END ====================\n"
        )

    if locale is not None:
        content = inject_survey_ui_i18n(content, locale)

    js_path.write_text(content, encoding="utf-8")
    print(f"Injected constants: {js_path}")


def _apply_question_list_region(
    html: str,
    questions: list[QuestionSpec],
    *,
    default_scale_options: list[dict[str, Any]] | None = None,
    default_matrix_columns: list[dict[str, Any]] | None = None,
    locale: str | None = None,
) -> str:
    blocks = []
    current_page = 0
    page_break_template = html_dict_for_locale(locale)["pageBreak"]
    for i, q in enumerate(questions, start=1):
        if q.page != current_page:
            current_page = q.page
            blocks.append(
                f'<div class="pb" data-page-break="{current_page}"><span>'
                f'{page_break_template.replace("{n}", str(current_page))}</span></div>'
            )
        blocks.append(build_question_html(
            q,
            i,
            default_scale_options=default_scale_options,
            default_matrix_columns=default_matrix_columns,
            locale=locale,
        ))
    question_area = "\n".join(blocks)
    pattern = r"(<!-- QUESTION_LIST_START:.*?-->)(.*?)(<!-- QUESTION_INSERT_POINT:.*?-->)"
    replaced = re.sub(pattern, rf"\1\n{question_area}\n    \3", html, flags=re.S)
    if replaced == html:
        raise ValueError(
            "The section between the question-area anchors <!-- QUESTION_LIST_START:...--> "
            "and <!-- QUESTION_INSERT_POINT:...--> was not found; do not delete or modify "
            "the QUESTION_LIST_START / QUESTION_INSERT_POINT keywords in those two comments."
        )
    return replaced


def _ensure_survey_ui_resources(html: str) -> str:
    """确保 HTML 中包含 survey-ui.css、sortable.js、survey-bridge.js 和 survey-ui.js 的引用；若缺失则自动插入。"""
    # CSS
    if not re.search(r'survey-ui\.css', html, re.IGNORECASE):
        if '<link' in html:
            html = re.sub(r'(<link[^>]*>)', r'<!-- survey-ui.css（问卷样式层） -->\n    <link rel="stylesheet" href="./survey-ui.css" data-inject="survey-css">\n    \1', html, count=1)
        else:
            html = html.replace('</head>', '    <!-- survey-ui.css（问卷样式层） -->\n    <link rel="stylesheet" href="./survey-ui.css" data-inject="survey-css">\n</head>')

    # survey-ui.js（head 内，问卷逻辑层）
    has_ui_js = re.search(r'src=["\'][^"\']*survey-ui\.js["\']', html, re.IGNORECASE)
    if not has_ui_js:
        if '</head>' in html:
            html = html.replace('</head>', '    <!-- survey-ui.js（问卷逻辑层） -->\n    <script src="./survey-ui.js" data-inject="survey-js" defer></script>\n</head>')

    # survey-bridge.js（head 内，问卷数据层）
    if not re.search(r'survey-bridge(?:-[^"\']+)?\.js', html, re.IGNORECASE):
        if '</head>' in html:
            html = html.replace('</head>', '    <!-- survey-bridge.js（问卷数据层）（一般情况下不需读取及修改） -->\n    <script src="https://wejot-pro.oss-cn-shenzhen.aliyuncs.com/jscript/_agent_uploads/survey-bridge-20260823-1.js"></script>\n</head>')

    # Sortable.js（head 内，拖拽组件）
    if not re.search(r'sortablejs', html, re.IGNORECASE):
        if '</head>' in html:
            html = html.replace('</head>', '    <!-- Sortable.js（拖拽组件）（一般情况下不需读取及修改） -->\n    <script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js"></script>\n</head>')

    return html


def build_survey_html(
    spec: dict[str, Any],
    questions: list[QuestionSpec],
    *,
    base_html: str,
    json_template: dict[str, Any] | None = None,
    locale: str | None = None,
) -> str:
    """Refresh the title and question-list region on base_html (constants moved to survey-ui.js)."""
    tmpl = json_template if json_template is not None else load_system_json_template()
    ds = localized_default_scale_options(locale) or (tmpl.get("scaleQuestions") or [{}])[0].get("options") or []
    dm = localized_default_scale_options(locale, matrix=True) or (
        tmpl.get("matrixScaleQuestions") or [{}]
    )[0].get("columns") or []
    html = base_html
    html = _apply_shell_locale(html, locale)
    html = _apply_survey_titles(html, spec, locale=locale)
    html = _apply_question_list_region(
        html,
        questions,
        default_scale_options=ds,
        default_matrix_columns=dm,
        locale=locale,
    )
    html = _ensure_survey_ui_resources(html)
    return html


def _apply_shell_locale(html: str, locale: str | None) -> str:
    """按回答端语种替换模板中硬编码的壳文案（导航按钮、<html lang>）。"""
    ui = html_dict_for_locale(locale)
    continue_label = ui.get("continue") or "继续"
    html = re.sub(
        r'(<button class="bs" id="nextBtn"[^>]*>)[^<]*(</button>)',
        lambda m: f"{m.group(1)}{continue_label}{m.group(2)}",
        html,
    )
    lang = str(locale or "zh-CN")
    html = re.sub(r'<html\s+lang="[^"]*"', f'<html lang="{html_escape(lang, quote=True)}"', html, count=1)
    return html


def build_html(
    spec: dict[str, Any],
    template_html: str,
    questions: list[QuestionSpec],
    json_template: dict[str, Any] | None = None,
    locale: str | None = None,
) -> str:
    """从完整模板 HTML 生成输出（兼容历史调用：等价于对系统模板做一次 build_survey_html）。"""
    return build_survey_html(
        spec, questions, base_html=template_html, json_template=json_template, locale=locale
    )


_TYPE_TO_SCHEMA_BUCKET: dict[str, str] = {
    "RADIO": "radioQuestions",
    "CHECKBOX": "checkboxQuestions",
    "TEXTAREA": "textQuestions",
    "UPLOAD": "uploadQuestions",
    "SCALE": "scaleQuestions",
    "MATRIX_SCALE": "matrixScaleQuestions",
    "GENERIC": "genericQuestions",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True, help="path to survey_spec.json")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="output directory; defaults to the --spec directory",
    )
    parser.add_argument(
        "--locale",
        default=None,
        help="respondent-side UI copy locale (e.g. zh-CN / en-US / es-MX). By default it is not overridden; the template's built-in zh-CN is used.",
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
    output_dir = resolve_work_dir(args.output_dir) if args.output_dir else spec_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    output_json_path = output_dir / OUTPUT_JSON_NAME
    output_html_path = output_dir / OUTPUT_HTML_NAME

    spec = load_json(spec_path)
    try:
        validate_spec_structure(spec, require_survey=True)
        validate_spec_chart_html(spec)
    except ValueError as e:
        print(f"Error: invalid spec structure.\n{e}", file=sys.stderr)
        sys.exit(1)
    if not spec.get("questions"):
        print(
            "Note: the current spec has 0 questions; the artifacts will contain only the survey title/description.",
            file=sys.stderr,
        )
    tmpl_json = load_system_json_template()
    questions = parse_questions(spec, locale=args.locale)
    out_json = build_schema(spec, tmpl_json, questions, locale=args.locale)

    if output_html_path.is_file():
        base_html = output_html_path.read_text(encoding="utf-8")
    else:
        base_html = SYSTEM_HTML_TEMPLATE_PATH.read_text(encoding="utf-8")
    out_html = build_survey_html(
        spec, questions, base_html=base_html, json_template=tmpl_json, locale=args.locale
    )
    output_json_path.write_text(json.dumps(out_json, ensure_ascii=False, indent=2), encoding="utf-8")
    output_html_path.write_text(out_html, encoding="utf-8")
    _ensure_survey_ui_css(output_dir)
    _inject_constants_into_survey_ui_js(
        output_dir,
        generate_option_value_constants(questions, locale=args.locale),
        locale=args.locale,
    )
    print(f"Generated: {output_json_path}")
    print(f"Generated: {output_html_path}")


if __name__ == "__main__":
    main()
