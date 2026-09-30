#!/usr/bin/env python3
"""从简化配置生成完整的 survey_spec.json

用途：
- 标准题型（RADIO/CHECKBOX/TEXTAREA/UPLOAD/SCALE/MATRIX_SCALE）只需提供核心字段，脚本自动补全
- GENERIC 题型需要提供完整的 genericHtml/genericScript/genericStyle
- 支持题目任意顺序混排

输入格式（simple_config.json）：
{
  "survey": {
    "title": "问卷标题",
    "description": "问卷描述"
  },
  "questions": [
    {
      "type": "RADIO",
      "title": "题目标题",
      "options": ["选项1", "选项2"],
      "required": true,
      "page": 1,
      "description": "题目描述（可选）",
      "code": "question_code（可选，自动生成）"
    },
    {
      "type": "GENERIC",
      "title": "自定义题",
      "required": false,
      "page": 1,
      "answerKeys": ["answer"],
      "genericHtml": "...",
      "genericScript": "...",
      "genericStyle": "...",
      "userAnswersSample": [...],
      "chartHtml": "..."
    }
  ]
}

输出：完整的 survey_spec.json（可直接传给 generate_standard_survey.py）
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from utils.checkbox_choices import checkbox_option_count, normalize_checkbox_choices


def gen_uuid() -> str:
    return uuid.uuid4().hex


def normalize_code(text: str) -> str:
    """生成规范化的题目 code"""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or f"q_{gen_uuid()[:8]}"


def auto_complete_standard_question(q: dict[str, Any], index: int) -> dict[str, Any]:
    """自动补全标准题型的必需字段"""
    qtype = str(q["type"]).upper()

    # 基础字段
    result: dict[str, Any] = {
        "title": q["title"],
        "type": qtype,
        "required": q.get("required", False),
        "page": q.get("page", 1),
        "code": q.get("code") or normalize_code(q["title"]),
        "description": q.get("description", ""),
    }

    # 按题型补全特定字段
    if qtype == "RADIO":
        if "options" not in q or not q["options"]:
            raise ValueError(f"RADIO 题型必须提供 options: {q['title']}")
        result["options"] = q["options"]
        if q.get("otherOption"):
            result["otherOption"] = True

    elif qtype == "CHECKBOX":
        if "options" not in q or not q["options"]:
            raise ValueError(f"CHECKBOX 题型必须提供 options: {q['title']}")
        result["options"] = q["options"]
        opt_count = checkbox_option_count(
            q["options"], other_option=bool(q.get("otherOption"))
        )
        min_c, max_c = normalize_checkbox_choices(
            q.get("minChoices"), q.get("maxChoices"), option_count=opt_count
        )
        result["minChoices"] = min_c
        result["maxChoices"] = max_c
        if q.get("otherOption"):
            result["otherOption"] = True

    elif qtype == "TEXTAREA":
        result["placeholder"] = q.get("placeholder", "请输入...")
        result["minLength"] = q.get("minLength", 0)
        result["maxLength"] = q.get("maxLength", 500)

    elif qtype == "UPLOAD":
        result["maxFileCount"] = q.get("maxFileCount", 1)
        result["maxFileSize"] = q.get("maxFileSize", 102400)
        result["fileTypes"] = q.get("fileTypes", ["jpg", "jpeg", "png", "pdf"])

    elif qtype == "SCALE":
        # SCALE 题型使用默认的 5 分量表，不需要额外配置
        pass

    elif qtype == "MATRIX_SCALE":
        if "rows" not in q or not q["rows"]:
            raise ValueError(f"MATRIX_SCALE 题型必须提供 rows: {q['title']}")
        result["rows"] = q["rows"]

    else:
        raise ValueError(f"不支持的标准题型: {qtype}")

    return result


def auto_complete_generic_question(q: dict[str, Any], index: int) -> dict[str, Any]:
    """验证并补全 GENERIC 题型的必需字段"""
    required_fields = ["genericHtml", "genericScript", "genericStyle"]
    missing = [f for f in required_fields if f not in q or not q[f]]
    if missing:
        raise ValueError(f"GENERIC 题型缺少必需字段 {missing}: {q['title']}")

    result: dict[str, Any] = {
        "title": q["title"],
        "type": "GENERIC",
        "required": q.get("required", False),
        "page": q.get("page", 1),
        "code": q.get("code") or normalize_code(q["title"]),
        "description": q.get("description", ""),
        "answerKeys": q.get("answerKeys", ["value"]),
        "userAnswersSample": q.get("userAnswersSample", []),
        "chartHtml": q.get("chartHtml", ""),
        "genericStyle": q["genericStyle"],
        "genericHtml": q["genericHtml"],
        "genericScript": q["genericScript"],
    }

    return result


def generate_survey_spec(simple_config: dict[str, Any]) -> dict[str, Any]:
    """从简化配置生成完整的 survey_spec.json"""
    spec = {
        "survey": {
            "title": simple_config["survey"]["title"],
            "description": simple_config["survey"].get("description", "")
        },
        "questions": []
    }

    # 按顺序处理每个题目
    for index, q in enumerate(simple_config["questions"], start=1):
        qtype = str(q["type"]).upper()

        if qtype == "GENERIC":
            completed = auto_complete_generic_question(q, index)
        else:
            completed = auto_complete_standard_question(q, index)

        spec["questions"].append(completed)

    return spec


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从简化配置生成完整的 survey_spec.json"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="简化配置文件路径（simple_config.json）"
    )
    parser.add_argument(
        "--output",
        default=None,
        help="输出文件路径（默认为输入文件同目录下的 survey_spec.json）"
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    output_path = (
        Path(args.output) if args.output
        else input_path.parent / "survey_spec.json"
    )

    # 读取简化配置
    simple_config = json.loads(input_path.read_text(encoding="utf-8"))

    # 生成完整 spec
    survey_spec = generate_survey_spec(simple_config)

    # 写入输出文件
    output_path.write_text(
        json.dumps(survey_spec, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"✓ 已生成: {output_path}")
    print(f"  题目总数: {len(survey_spec['questions'])}")

    # 统计题型分布
    type_counts: dict[str, int] = {}
    for q in survey_spec["questions"]:
        qtype = q["type"]
        type_counts[qtype] = type_counts.get(qtype, 0) + 1

    print("  题型分布:")
    for qtype, count in sorted(type_counts.items()):
        print(f"    {qtype}: {count}")


if __name__ == "__main__":
    main()
