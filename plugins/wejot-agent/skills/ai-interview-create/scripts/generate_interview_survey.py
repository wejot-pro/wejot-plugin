#!/usr/bin/env python3
"""从 question_schema_generate.json 归一化并生成 AI 访谈引导页产物。

常规路径：读写工作目录下 question_schema_generate.json，派生 HTML/css/js，
并内嵌调用 validate_interview_survey 完成验收。HTML 仅为同源答题宿主引导页。
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from load_interview_json import DuplicateSurveyKeyError, load_interview_json_file
from upload_file_types import normalize_file_types
from validate_interview_survey import (
    _validate_scale_score_sequence,
    validate_dir,
    validate_java_schema,
)

JAVA_QUESTION_ARRAYS = (
    "textQuestions",
    "radioQuestions",
    "checkboxQuestions",
    "scaleQuestions",
    "matrixScaleQuestions",
    "uploadQuestions",
    "interviewQuestions",
    "interactiveQuestions",
)
ARRAY_TO_TYPE = {
    "textQuestions": "INPUT",
    "radioQuestions": "RADIO",
    "checkboxQuestions": "CHECKBOX",
    "scaleQuestions": "SCALE",
    "matrixScaleQuestions": "MATRIX_SCALE",
    "uploadQuestions": "UPLOAD",
    "interviewQuestions": "INTERVIEW",
    "interactiveQuestions": "INTERACTIVE",
}
FOLLOWUP_MODES = {"none", "one", "two_three", "open", "logic"}
MODES = {"phone", "chat"}
DEFAULT_UPLOAD_FILE_TYPES = [
    "jpg", "jpeg", "gif", "png", "bmp", "zip", "rar",
    "mp3", "mp4", "mov",
    "doc", "docx", "xls", "xlsx", "csv", "ppt", "pptx", "pdf",
]
DEFAULT_UPLOAD_MAX_FILE_COUNT = 1
DEFAULT_UPLOAD_MAX_FILE_SIZE_KB = 102400
SCHEMA_FILENAME = "question_schema_generate.json"


def _media_mode(default_mode: str, recording: dict[str, Any]) -> str:
    if default_mode == "chat":
        return "text"
    if _bool(recording.get("video"), True):
        return "video"
    return "audio"


def _text(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _required_int(value: Any, default: int = 1) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int) and value in (0, 1):
        return value
    if isinstance(value, str) and value.strip() in {"0", "1"}:
        return int(value.strip())
    return default


def _first_text(*values: Any, default: str = "") -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value
    return default


def _iter_question_entries(raw: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    entries: list[tuple[str, dict[str, Any]]] = []
    for array_key in JAVA_QUESTION_ARRAYS:
        arr = raw.get(array_key)
        if not isinstance(arr, list):
            continue
        for q in arr:
            if isinstance(q, dict):
                entries.append((array_key, q))
    entries.sort(key=lambda pair: int(pair[1].get("sort") or 0))
    return entries


def _choice_options(options: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, opt in enumerate(options or [], start=1):
        if isinstance(opt, str):
            out.append({"sort": i, "label": opt.strip()})
            continue
        if isinstance(opt, dict):
            label = _text(opt.get("label") or opt.get("title") or opt.get("text"), f"选项{i}")
            item: dict[str, Any] = {"sort": i, "label": label}
            desc = opt.get("description")
            if isinstance(desc, str) and desc.strip():
                item["description"] = desc
            out.append(item)
            continue
        out.append({"sort": i, "label": f"选项{i}"})
    return out


def _scale_options(options: Any) -> list[dict[str, Any]]:
    """SCALE 仅允许 options[{sort, score, title}]，禁止 scale/scaleLabels。"""
    if not isinstance(options, list) or not options:
        raise ValueError("SCALE 题目必须提供非空 options（禁止 scale/scaleLabels）")
    out: list[dict[str, Any]] = []
    for i, opt in enumerate(options, start=1):
        if isinstance(opt, dict):
            sort = int(opt["sort"]) if isinstance(opt.get("sort"), int) else i
            title = _text(opt.get("title") or opt.get("label"), str(i))
            if opt.get("score") is None:
                raise ValueError(f"SCALE options[{i}].score 为必填")
            score = opt["score"]
            if not isinstance(score, int) or isinstance(score, bool):
                raise ValueError(f"SCALE options[{i}].score 必须为整数")
            if not title.strip():
                raise ValueError(f"SCALE options[{i}].title 为必填")
            out.append({"sort": sort, "score": score, "title": title})
        else:
            raise ValueError(f"SCALE options[{i}] 必须是含 sort/score/title 的对象")
    sequence_errors = _validate_scale_score_sequence(out, "SCALE")
    if sequence_errors:
        raise ValueError(sequence_errors[0])
    return out


def _matrix_columns(columns: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, col in enumerate(columns or [], start=1):
        if isinstance(col, str):
            out.append({"sort": i, "score": float(i), "title": col.strip()})
            continue
        if isinstance(col, dict):
            title = _text(
                col.get("title") or col.get("columnTitle") or col.get("label"),
                f"列{i}",
            )
            score = float(col["score"]) if col.get("score") is not None else float(i)
            out.append({"sort": i, "score": score, "title": title})
            continue
        out.append({"sort": i, "score": float(i), "title": f"列{i}"})
    return out


def _matrix_rows(rows: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows or [], start=1):
        if isinstance(row, str):
            out.append({"sort": i, "title": row.strip()})
            continue
        if isinstance(row, dict):
            title = _text(
                row.get("title") or row.get("rowTitle") or row.get("label"),
                f"行{i}",
            )
            out.append({"sort": i, "title": title})
            continue
        out.append({"sort": i, "title": f"行{i}"})
    return out


def _copy_optional_int01(dst: dict[str, Any], src: dict[str, Any], key: str) -> None:
    if key not in src:
        return
    value = src[key]
    if isinstance(value, bool):
        dst[key] = 1 if value else 0
        return
    if isinstance(value, int) and value in (0, 1):
        dst[key] = value
        return
    if isinstance(value, str) and value.strip() in {"0", "1"}:
        dst[key] = int(value.strip())


def _copy_optional_positive_int(dst: dict[str, Any], src: dict[str, Any], key: str) -> None:
    if key not in src:
        return
    value = src[key]
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        dst[key] = value


def _copy_optional_text(dst: dict[str, Any], src: dict[str, Any], key: str) -> None:
    if key not in src:
        return
    if isinstance(src[key], str):
        dst[key] = src[key]


def normalize_spec(raw: dict[str, Any]) -> dict[str, Any]:
    if "questions" in raw:
        raise ValueError("禁止根级 questions[]；请使用 radioQuestions 等按题型分组数组")
    if "schemaVersion" in raw:
        raise ValueError("禁止 schemaVersion")

    survey = raw.get("survey") if isinstance(raw.get("survey"), dict) else {}
    allowed_modes = survey.get("allowedModes")
    if not isinstance(allowed_modes, list) or not allowed_modes:
        allowed_modes = ["phone", "chat"]
    allowed_modes = [m for m in allowed_modes if m in MODES] or ["phone", "chat"]
    default_mode = survey.get("defaultMode")
    if default_mode not in allowed_modes:
        default_mode = allowed_modes[0]

    recording = survey.get("recording") if isinstance(survey.get("recording"), dict) else {}
    input_settings = survey.get("input") if isinstance(survey.get("input"), dict) else {}
    brand_info = survey.get("brandInfo") if isinstance(survey.get("brandInfo"), dict) else {}
    media_mode = survey.get("mediaMode")
    if media_mode not in {"text", "audio", "video"}:
        media_mode = _media_mode(default_mode, recording)

    normalized: dict[str, Any] = {
        "survey": {
            "kind": "AI_INTERVIEW",
            "title": _text(survey.get("title"), "AI 访谈"),
            "description": _text(survey.get("description")),
            "welcomeMessage": _first_text(
                survey.get("welcomeMessage"),
                survey.get("introMessage"),
                survey.get("openingMessage"),
                survey.get("description"),
            ),
            "outroMessage": _first_text(survey.get("outroMessage")),
            "mediaMode": media_mode,
            "language": _text(survey.get("language"), "zh-CN"),
            "allowedModes": allowed_modes,
            "defaultMode": default_mode,
            "recording": {
                "audio": _bool(recording.get("audio"), True),
                "video": _bool(recording.get("video"), True),
            },
            "input": {
                "keyboard": _bool(input_settings.get("keyboard"), False),
            },
            "brandInfo": {
                "brandName": _text(brand_info.get("brandName")),
                "logoUrl": _text(brand_info.get("logoUrl")),
            },
            "background": _text(survey.get("background")),
            "requirements": _text(survey.get("requirements")),
        },
    }

    buckets: dict[str, list[dict[str, Any]]] = {key: [] for key in JAVA_QUESTION_ARRAYS}
    seen_uuids: set[str] = set()
    entries = _iter_question_entries(raw)
    for index, (array_key, q) in enumerate(entries, start=1):
        expected_type = ARRAY_TO_TYPE[array_key]
        qtype = str(q.get("type") or expected_type).upper()
        if qtype != expected_type:
            qtype = expected_type
        if "id" in q or "code" in q:
            raise ValueError(f"{array_key} 题目禁止 id/code 字段，题目标识请用 uuid")

        q_uuid = _text(q.get("uuid"), str(uuid.uuid4()))
        while q_uuid in seen_uuids:
            q_uuid = str(uuid.uuid4())
        seen_uuids.add(q_uuid)

        followup = q.get("followup") if isinstance(q.get("followup"), dict) else {}
        followup_mode = followup.get("mode") or q.get("followUpDepth") or q.get("followupDepth")
        if followup_mode not in FOLLOWUP_MODES:
            followup_mode = "two_three" if qtype in {"INTERVIEW", "INTERACTIVE"} else "none"
        followup_out: dict[str, Any] = {"mode": followup_mode}
        logic = _first_text(
            followup.get("logicPrompt"), q.get("logicPrompt"), q.get("followUpLogicPrompt")
        )
        if followup_mode == "logic" or logic.strip():
            followup_out["logicPrompt"] = logic

        title = _first_text(q.get("title"), q.get("question"), q.get("text"), default=f"第{index}题")
        base: dict[str, Any] = {
            "title": title,
            "description": _text(q.get("description")),
            "uuid": q_uuid,
            "required": _required_int(q.get("required"), 1),
            "sort": int(q.get("sort") or index * 1000),
            "type": qtype,
            "condition": _text(q.get("condition")),
            "guide": _first_text(q.get("guide"), q.get("interviewGuide"), q.get("questionGuide")),
            "followup": followup_out,
        }
        if "displayMedia" in q:
            base["displayMedia"] = q["displayMedia"]

        if qtype in {"RADIO", "CHECKBOX"}:
            base["options"] = _choice_options(q.get("options"))
            _copy_optional_int01(base, q, "otherEnabled")
            _copy_optional_text(base, q, "otherText")
            if qtype == "CHECKBOX":
                _copy_optional_positive_int(base, q, "minChoices")
                _copy_optional_positive_int(base, q, "maxChoices")
        elif qtype == "SCALE":
            if "scale" in q or "scaleLabels" in q:
                raise ValueError(
                    f"{array_key} SCALE 禁止 scale/scaleLabels，请直接写 options"
                    f"（{{ sort, score, title }}）"
                )
            base["options"] = _scale_options(q.get("options"))
        elif qtype == "MATRIX_SCALE":
            base["columns"] = _matrix_columns(q.get("columns"))
            base["rows"] = _matrix_rows(q.get("rows"))
        elif qtype == "UPLOAD":
            base["accept"] = _text(q.get("accept"), "*/*") or "*/*"
            base["maxFileCount"] = int(q.get("maxFileCount") or DEFAULT_UPLOAD_MAX_FILE_COUNT)
            base["maxFileSize"] = int(q.get("maxFileSize") or DEFAULT_UPLOAD_MAX_FILE_SIZE_KB)
            base["fileTypes"] = (
                normalize_file_types(q.get("fileTypes")) or list(DEFAULT_UPLOAD_FILE_TYPES)
            )

        buckets[array_key].append(base)

    for key, items in buckets.items():
        if items:
            normalized[key] = items
    return normalized


def count_questions(spec: dict[str, Any]) -> int:
    total = 0
    for key in JAVA_QUESTION_ARRAYS:
        arr = spec.get(key)
        if isinstance(arr, list):
            total += len(arr)
    return total


def render_bootstrap_html(schema: dict[str, Any]) -> str:
    title = html.escape(schema["survey"]["title"], quote=True)
    description = html.escape(schema["survey"].get("description") or "", quote=False)
    payload = html.escape(json.dumps(schema, ensure_ascii=False, separators=(",", ":")), quote=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="survey-kind" content="AI_INTERVIEW">
  <title>{title}</title>
  <link rel="stylesheet" href="./survey-ui.css" data-inject="survey-css">
  <script src="./survey-ui.js" data-inject="survey-js" defer></script>
</head>
<body data-survey-kind="AI_INTERVIEW">
  <main id="ai-interview-root" data-ai-interview-root>
    <noscript>请启用 JavaScript 后继续访谈。</noscript>
    <section data-ai-interview-fallback>
      <h1>{title}</h1>
      <p>{description}</p>
    </section>
  </main>
  <script id="ai-interview-spec" type="application/json">{payload}</script>
</body>
</html>
"""


def write_artifacts(schema: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(schema, ensure_ascii=False, indent=2) + "\n"
    (output_dir / SCHEMA_FILENAME).write_text(text, encoding="utf-8")
    (output_dir / "survey-unified-generate.html").write_text(
        render_bootstrap_html(schema),
        encoding="utf-8",
    )
    (output_dir / "survey-ui.css").write_text(
        ":root{color-scheme:light}body{margin:0;font-family:-apple-system,BlinkMacSystemFont,\"PingFang SC\",\"Microsoft YaHei\",sans-serif;background:#fff;color:#1f2329}\n",
        encoding="utf-8",
    )
    (output_dir / "survey-ui.js").write_text(
        "window.__WEJOT_AI_INTERVIEW_BOOTSTRAP__=true;\n"
        "window.parent&&window.parent.postMessage({type:'AI_INTERVIEW_SPEC_READY'},'*');\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="归一化 question_schema_generate.json 并生成引导页（含产物验收）"
    )
    parser.add_argument(
        "--dir",
        default=".",
        help="工作目录（须含 question_schema_generate.json；产物写回同目录）",
    )
    args = parser.parse_args()

    work_dir = Path(args.dir).resolve()
    schema_path = work_dir / SCHEMA_FILENAME
    if not schema_path.exists():
        print(f"ERROR: 缺少 {SCHEMA_FILENAME}: {schema_path}", file=sys.stderr)
        return 2

    try:
        raw = load_interview_json_file(schema_path)
    except DuplicateSurveyKeyError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"读取 {SCHEMA_FILENAME} 失败: {exc}", file=sys.stderr)
        return 2
    if not isinstance(raw, dict):
        print(f"ERROR: {SCHEMA_FILENAME} 根节点必须是对象", file=sys.stderr)
        return 2

    try:
        schema = normalize_spec(raw)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    pre_errors = validate_java_schema(schema, label=SCHEMA_FILENAME)
    if pre_errors:
        for error in pre_errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    write_artifacts(schema, work_dir)

    post_errors = validate_dir(work_dir)
    if post_errors:
        for error in post_errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(json.dumps({
        "ok": True,
        "kind": "AI_INTERVIEW",
        "questions": count_questions(schema),
        "outputDir": str(work_dir),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
