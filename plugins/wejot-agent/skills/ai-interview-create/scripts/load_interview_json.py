"""加载 AI 访谈 JSON：重复 survey 报错；重复 *Questions 静默合并。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

QUESTION_ARRAY_KEYS = frozenset(
    {
        "textQuestions",
        "radioQuestions",
        "checkboxQuestions",
        "scaleQuestions",
        "matrixScaleQuestions",
        "uploadQuestions",
        "interviewQuestions",
        "interactiveQuestions",
    }
)


class DuplicateSurveyKeyError(ValueError):
    """根节点出现多个 survey key。"""


def merge_interview_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """json.loads object_pairs_hook：survey 禁止重复；题型桶 list 静默 extend。"""
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key == "survey":
            if "survey" in out:
                raise DuplicateSurveyKeyError(
                    "根节点 survey 只能出现一次，禁止重复 key"
                )
            out[key] = value
            continue
        if key in QUESTION_ARRAY_KEYS:
            if key in out:
                existing = out[key]
                if isinstance(existing, list) and isinstance(value, list):
                    existing.extend(value)
                    continue
                raise ValueError(
                    f"根节点 {key} 重复且无法合并（两侧须均为数组）"
                )
            out[key] = value
            continue
        out[key] = value
    return out


def loads_interview_json(text: str) -> Any:
    return json.loads(text, object_pairs_hook=merge_interview_object_pairs)


def load_interview_json_file(path: Path) -> Any:
    return loads_interview_json(path.read_text(encoding="utf-8-sig"))
