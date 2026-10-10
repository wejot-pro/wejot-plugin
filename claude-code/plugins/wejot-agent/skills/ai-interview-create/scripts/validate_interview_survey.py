#!/usr/bin/env python3
"""校验 AI 访谈问卷产物（question_schema_generate.json + 引导页 HTML）。

供 generate_interview_survey.py import 复用；CLI 用于未跑 generate、直接手改产物时的补救验收。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from load_interview_json import DuplicateSurveyKeyError, load_interview_json_file
from upload_file_types import ALLOWED_FILE_EXTENSIONS

WELCOME_START_CONFIRMATION_RE = re.compile(
    r"("
    r"[?？]"
    r"|是否|方便|可以开始|准备好|开始吗|开始吧|现在开始"
    r"|convenient|ready|shall we begin|can we begin|start now"
    r"|始め|始めても|よろしい|大丈夫|괜찮|시작|พร้อม|สะดวก"
    r")",
    re.IGNORECASE,
)

JAVA_QUESTION_ARRAYS = {
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


def _load_json(path: Path) -> tuple[dict | None, list[str]]:
    try:
        data = load_interview_json_file(path)
    except DuplicateSurveyKeyError as exc:
        return None, [f"{path.name}: {exc}"]
    except Exception as exc:
        return None, [f"{path.name}: JSON 无效: {exc}"]
    if not isinstance(data, dict):
        return None, [f"{path.name}: 根节点必须是对象"]
    return data, []


def _asks_start_confirmation(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return bool(WELCOME_START_CONFIRMATION_RE.search(value.strip()))


def _validate_followup(followup: object, prefix: str, required: bool) -> list[str]:
    errors: list[str] = []
    if followup is None:
        if required:
            errors.append(f"{prefix}.followup 为必填")
        return errors
    if not isinstance(followup, dict):
        errors.append(f"{prefix}.followup 必须是对象")
        return errors
    mode = followup.get("mode")
    if mode not in FOLLOWUP_MODES:
        errors.append(f"{prefix}.followup.mode 无效")
    elif mode == "logic" and not str(followup.get("logicPrompt") or "").strip():
        errors.append(f"{prefix}.followup.logicPrompt 在 mode=logic 时为必填")
    return errors


def _validate_common_question(q: dict, prefix: str, expected_type: str) -> list[str]:
    errors: list[str] = []
    if q.get("type") != expected_type:
        errors.append(f"{prefix}.type 必须为 {expected_type}")
    if not isinstance(q.get("title"), str) or not q["title"].strip():
        errors.append(f"{prefix}.title 为必填")
    if not isinstance(q.get("uuid"), str) or not q["uuid"]:
        errors.append(f"{prefix}.uuid 为必填")
    if "id" in q:
        errors.append(f"{prefix} 不得包含 id")
    if "code" in q:
        errors.append(f"{prefix} 不得包含 code")
    if q.get("required") not in (0, 1):
        errors.append(f"{prefix}.required 必须为 0 或 1")
    if not isinstance(q.get("sort"), int):
        errors.append(f"{prefix}.sort 必须为整数")
    need_followup = expected_type in {"INTERVIEW", "INTERACTIVE"}
    errors.extend(_validate_followup(q.get("followup"), prefix, required=need_followup))
    return errors


def _validate_scale_score_sequence(options: list[dict], prefix: str) -> list[str]:
    """SCALE 按 sort 展示顺序只允许连续整数分值 1..N。"""
    if not all(
        isinstance(opt, dict)
        and isinstance(opt.get("sort"), int)
        and not isinstance(opt.get("sort"), bool)
        and isinstance(opt.get("score"), int)
        and not isinstance(opt.get("score"), bool)
        for opt in options
    ):
        return []
    actual = [opt["score"] for opt in sorted(options, key=lambda opt: opt["sort"])]
    expected = list(range(1, len(options) + 1))
    if actual != expected:
        return [
            f"{prefix}.options 按 sort 升序后的 score 必须从 1 开始、连续且严格递增；"
            f"期望 {expected}，实际 {actual}"
        ]
    return []


def validate_java_schema(schema: dict, *, label: str = "schema") -> list[str]:
    errors: list[str] = []
    if "schemaVersion" in schema:
        errors.append(f"{label}: 根节点不得包含 schemaVersion")
    if "questions" in schema:
        errors.append(f"{label}: 根节点不得包含统一 questions[]；请按题型使用 *Questions 数组")

    survey = schema.get("survey")
    if not isinstance(survey, dict):
        errors.append(f"{label}: survey 必须是对象")
        survey = {}
    if survey.get("kind") != "AI_INTERVIEW":
        errors.append(f"{label}: survey.kind 必须为 AI_INTERVIEW")
    for key in ("title", "description", "welcomeMessage", "outroMessage"):
        if not isinstance(survey.get(key), str):
            errors.append(f"{label}: survey.{key} 必须为字符串")
        elif key != "description" and not survey[key].strip():
            errors.append(f"{label}: survey.{key} 为必填")
    if isinstance(survey.get("welcomeMessage"), str) and survey["welcomeMessage"].strip():
        if not _asks_start_confirmation(survey.get("welcomeMessage")):
            errors.append(f"{label}: survey.welcomeMessage 须询问是否方便开始或是否准备好开始")
    if survey.get("mediaMode") not in {"text", "audio", "video"}:
        errors.append(f"{label}: survey.mediaMode 必须为 text/audio/video")
    if not isinstance(survey.get("allowedModes"), list) or not survey["allowedModes"]:
        errors.append(f"{label}: survey.allowedModes 须包含 phone/chat")
    if survey.get("defaultMode") not in (survey.get("allowedModes") or []):
        errors.append(f"{label}: survey.defaultMode 必须属于 allowedModes")
    brand_info = survey.get("brandInfo")
    if brand_info is not None:
        if not isinstance(brand_info, dict):
            errors.append(f"{label}: survey.brandInfo 必须是对象")
        else:
            for key in ("brandName", "logoUrl"):
                if brand_info.get(key) is not None and not isinstance(brand_info.get(key), str):
                    errors.append(f"{label}: survey.brandInfo.{key} 必须为字符串")

    uuids: set[str] = set()
    total = 0

    for array_key, expected_type in JAVA_QUESTION_ARRAYS.items():
        arr = schema.get(array_key)
        if arr is None:
            continue
        if not isinstance(arr, list):
            errors.append(f"{label}: {array_key} 必须是数组")
            continue
        for idx, q in enumerate(arr, start=1):
            prefix = f"{label}.{array_key}[{idx}]"
            if not isinstance(q, dict):
                errors.append(f"{prefix} 必须是对象")
                continue
            total += 1
            errors.extend(_validate_common_question(q, prefix, expected_type))
            q_uuid = q.get("uuid")
            if isinstance(q_uuid, str) and q_uuid:
                if q_uuid in uuids:
                    errors.append(f"{prefix}.uuid 重复: {q_uuid}")
                else:
                    uuids.add(q_uuid)

            if expected_type in {"RADIO", "CHECKBOX"}:
                options = q.get("options")
                if not isinstance(options, list) or not options:
                    errors.append(f"{prefix}.options 为必填")
                else:
                    for oi, opt in enumerate(options, start=1):
                        op = f"{prefix}.options[{oi}]"
                        if not isinstance(opt, dict):
                            errors.append(f"{op} 必须是对象")
                            continue
                        if not isinstance(opt.get("sort"), int):
                            errors.append(f"{op}.sort 为必填整数")
                        if not isinstance(opt.get("label"), str) or not opt["label"].strip():
                            errors.append(f"{op}.label 为必填")
                        if "title" in opt or "value" in opt:
                            errors.append(f"{op} 请使用 label，勿使用 title/value")

            if expected_type == "SCALE":
                if "scale" in q or "scaleLabels" in q:
                    errors.append(f"{prefix} 禁止 scale/scaleLabels，须使用 options")
                options = q.get("options")
                if not isinstance(options, list) or not options:
                    errors.append(f"{prefix}.options 为必填")
                else:
                    for oi, opt in enumerate(options, start=1):
                        op = f"{prefix}.options[{oi}]"
                        if not isinstance(opt, dict):
                            errors.append(f"{op} 必须是对象")
                            continue
                        if not isinstance(opt.get("sort"), int):
                            errors.append(f"{op}.sort 为必填整数")
                        if not isinstance(opt.get("score"), int) or isinstance(opt.get("score"), bool):
                            errors.append(f"{op}.score 为必填整数")
                        if not isinstance(opt.get("title"), str) or not opt["title"].strip():
                            errors.append(f"{op}.title 为必填")
                    errors.extend(_validate_scale_score_sequence(options, prefix))

            if expected_type in {"RADIO", "CHECKBOX"}:
                if "otherEnabled" in q and q["otherEnabled"] not in (0, 1):
                    errors.append(f"{prefix}.otherEnabled 必须为 0 或 1")
                if "otherText" in q and not isinstance(q.get("otherText"), str):
                    errors.append(f"{prefix}.otherText 必须为字符串")

            if expected_type == "CHECKBOX":
                for key in ("minChoices", "maxChoices"):
                    if key in q and (
                        not isinstance(q.get(key), int)
                        or isinstance(q.get(key), bool)
                        or q[key] < 1
                    ):
                        errors.append(f"{prefix}.{key} 必须为正整数")
                if (
                    isinstance(q.get("minChoices"), int)
                    and isinstance(q.get("maxChoices"), int)
                    and q["minChoices"] > q["maxChoices"]
                ):
                    errors.append(f"{prefix}.minChoices 不得大于 maxChoices")

            if expected_type == "MATRIX_SCALE":
                if not isinstance(q.get("columns"), list) or not q["columns"]:
                    errors.append(f"{prefix}.columns 为必填")
                else:
                    for ci, col in enumerate(q["columns"], start=1):
                        cp = f"{prefix}.columns[{ci}]"
                        if not isinstance(col, dict):
                            errors.append(f"{cp} 必须是对象")
                            continue
                        if not isinstance(col.get("sort"), int):
                            errors.append(f"{cp}.sort 为必填整数")
                        if not isinstance(col.get("score"), (int, float)):
                            errors.append(f"{cp}.score 为必填数字")
                        if not (
                            (isinstance(col.get("columnTitle"), str) and col["columnTitle"].strip())
                            or (isinstance(col.get("title"), str) and col["title"].strip())
                            or (isinstance(col.get("label"), str) and col["label"].strip())
                        ):
                            errors.append(f"{cp} 须有 columnTitle/title/label 之一")
                if not isinstance(q.get("rows"), list) or not q["rows"]:
                    errors.append(f"{prefix}.rows 为必填")
                else:
                    for ri, row in enumerate(q["rows"], start=1):
                        rp = f"{prefix}.rows[{ri}]"
                        if not isinstance(row, dict):
                            errors.append(f"{rp} 必须是对象")
                            continue
                        if not isinstance(row.get("sort"), int):
                            errors.append(f"{rp}.sort 为必填整数")
                        if not (
                            (isinstance(row.get("rowTitle"), str) and row["rowTitle"].strip())
                            or (isinstance(row.get("title"), str) and row["title"].strip())
                            or (isinstance(row.get("label"), str) and row["label"].strip())
                        ):
                            errors.append(f"{rp} 须有 rowTitle/title/label 之一")

            if expected_type == "UPLOAD":
                for key in ("maxFileCount", "maxFileSize"):
                    if key not in q:
                        errors.append(f"{prefix}.{key} 为必填")
                    elif not isinstance(q.get(key), int) or q[key] <= 0:
                        errors.append(f"{prefix}.{key} 必须为正整数")
                file_types = q.get("fileTypes")
                if not isinstance(file_types, list) or not file_types:
                    errors.append(f"{prefix}.fileTypes 须为非空数组")
                else:
                    allowed = set(ALLOWED_FILE_EXTENSIONS)
                    bad = [
                        item
                        for item in file_types
                        if not isinstance(item, str)
                        or item.strip().lower().lstrip(".") not in allowed
                    ]
                    if bad:
                        errors.append(
                            f"{prefix}.fileTypes 含 Java 不支持的类型: {bad}；"
                            "须为无点小写扩展名且属于 UploadSurveyQuestionHandler.allowedExtensions"
                        )

    if total == 0:
        errors.append(f"{label}: 至少需要一道题目（任一 *Questions 数组非空）")
    return errors


def validate_html_file(html_path: Path) -> list[str]:
    errors: list[str] = []
    if not html_path.exists():
        errors.append(f"缺少产物: {html_path.name}")
        return errors
    html = html_path.read_text(encoding="utf-8")
    if 'data-survey-kind="AI_INTERVIEW"' not in html:
        errors.append("survey-unified-generate.html 须标记 data-survey-kind=AI_INTERVIEW")
    if 'id="ai-interview-spec"' not in html:
        errors.append("survey-unified-generate.html 须嵌入 ai-interview-spec JSON")
    if "survey-bridge.js" in html:
        errors.append("AI 访谈引导页不得直接加载旧版 survey-bridge.js")
    return errors


def validate_dir(work_dir: Path) -> list[str]:
    """验收工作目录产物（schema + 引导页 HTML）。"""
    errors: list[str] = []
    json_path = work_dir / "question_schema_generate.json"
    html_path = work_dir / "survey-unified-generate.html"

    if not json_path.exists():
        errors.append("缺少产物: question_schema_generate.json")
    if not html_path.exists():
        errors.append("缺少产物: survey-unified-generate.html")

    if json_path.exists():
        schema, json_errors = _load_json(json_path)
        errors.extend(json_errors)
        if schema:
            errors.extend(validate_java_schema(schema, label="question_schema_generate.json"))

    errors.extend(validate_html_file(html_path))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="校验 AI 访谈问卷产物（手改 JSON/HTML 且未跑 generate 时使用）"
    )
    parser.add_argument("--dir", default=".", help="包含已生成产物的目录")
    args = parser.parse_args()
    errors = validate_dir(Path(args.dir))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "kind": "AI_INTERVIEW"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
