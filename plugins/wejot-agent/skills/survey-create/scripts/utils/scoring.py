"""计分 config 解析与可计分题过滤。"""

from __future__ import annotations

import re

from .html_questions import QuestionMeta

TYPE_NAME_TO_NUM: dict[str, str] = {
    "TEXTAREA": "1",
    "RADIO": "8",
    "CHECKBOX": "9",
    "SCALE": "10",
    "UPLOAD": "15",
    "MATRIX_SCALE": "28",
    "GENERIC": "39",
}

NUM_TO_TYPE_NAME: dict[str, str] = {v: k for k, v in TYPE_NAME_TO_NUM.items()}

DEFAULT_AUTO_EXCLUDE_TYPES = ("TEXTAREA", "UPLOAD")

_SCORING_META_KEYS = frozenset({
    "model", "autoExcludeTypes", "excludeQuestionCodes", "maxScore", "rules", "mapping",
})

_OPT_CODE_RE = re.compile(r"_opt_\d+", re.I)


def scoring_by_uuid(scoring_map: dict, code2uuid: dict[str, str]) -> dict:
    """把 scoring.mapping（按题 code）转成按 uuid。"""
    by_uuid: dict = {}
    for code, opt_map in (scoring_map or {}).items():
        uuid = code2uuid.get(code, code)
        by_uuid[uuid] = opt_map
    return by_uuid


def _type_nums_for_names(type_names: list[str]) -> set[str]:
    nums: set[str] = set()
    for name in type_names:
        key = str(name).strip().upper()
        if key in TYPE_NAME_TO_NUM:
            nums.add(TYPE_NAME_TO_NUM[key])
        elif key.isdigit():
            nums.add(key)
    return nums


def resolve_scorable_codes(config: dict, questions: list[QuestionMeta]) -> list[str]:
    """返回参与 eval_result 计分的题目 code 列表（保持 DOM 顺序）。"""
    scoring_cfg = config.get("scoring") or {}
    auto_exclude = scoring_cfg.get("autoExcludeTypes")
    if auto_exclude is None:
        exclude_type_names = list(DEFAULT_AUTO_EXCLUDE_TYPES)
    else:
        exclude_type_names = [str(x) for x in auto_exclude]
    exclude_type_nums = _type_nums_for_names(exclude_type_names)
    exclude_codes = set(str(c) for c in (scoring_cfg.get("excludeQuestionCodes") or []))

    scorable: list[str] = []
    for code, _uuid, tnum in questions:
        if code in exclude_codes:
            continue
        if tnum in exclude_type_nums:
            continue
        scorable.append(code)
    return scorable


def get_scoring_mapping(scoring_cfg: dict) -> dict:
    """从 scoring 配置节取出按题 code 的分值映射。"""
    if not scoring_cfg:
        return {}
    if "mapping" in scoring_cfg:
        return dict(scoring_cfg.get("mapping") or {})
    model = scoring_cfg.get("model")
    if model in (None, "sum"):
        return {k: v for k, v in scoring_cfg.items() if k not in _SCORING_META_KEYS}
    return {}


def _append_unique(warns: list[str], seen: set[str], message: str) -> None:
    if message in seen:
        return
    seen.add(message)
    warns.append(message)


def _warn_for_question_code_ref(
    code: str,
    *,
    all_codes: set[str],
    scorable_set: set[str],
    context: str,
    seen: set[str],
    warns: list[str],
) -> None:
    """根据题 code 引用生成更准确的 warn（去重）。"""
    if _OPT_CODE_RE.search(code):
        _append_unique(
            warns,
            seen,
            f"{context} 中 {code} 不是有效题 code（勿用 Q1_opt_1 格式）；"
            f"应写题 code（如 Q1），单选/多选按选项给分请用 sum 模式的 scoring.mapping（如 \"Q1\": {{\"1\": 10, \"2\": 0}}）",
        )
        return
    if code not in all_codes:
        sample = ", ".join(sorted(all_codes)[:8])
        suffix = "…" if len(all_codes) > 8 else ""
        _append_unique(
            warns,
            seen,
            f"{context} 引用了卷面不存在的题 code {code}（当前题为 {sample}{suffix}）",
        )
        return
    if code not in scorable_set:
        _append_unique(
            warns,
            seen,
            f"{context} 引用了不可自动记分的题 {code}（如 TEXTAREA/UPLOAD 或 excludeQuestionCodes），该题不参与 eval_result 计分",
        )


def check_unscorable_warnings(config: dict, questions: list[QuestionMeta], scorable_codes: list[str]) -> list[str]:
    """配置里引用了无效/不可自动记分题时的 warn（去重、措辞更准确）。"""
    warns: list[str] = []
    seen: set[str] = set()
    scorable_set = set(scorable_codes)
    all_codes = {code for code, _u, _t in questions}
    scoring_cfg = config.get("scoring") or {}
    model = scoring_cfg.get("model") or "sum"

    for code in get_scoring_mapping(scoring_cfg):
        _warn_for_question_code_ref(
            code,
            all_codes=all_codes,
            scorable_set=scorable_set,
            context="scoring.mapping",
            seen=seen,
            warns=warns,
        )

    if model == "rules":
        for rule in scoring_cfg.get("rules") or []:
            when = rule.get("when")
            if not isinstance(when, dict):
                continue
            refs: set[str] = set()
            for key in ("everyAllOptionsSelected", "everyNoneSelected"):
                refs.update(str(c) for c in (when.get(key) or []))
            cnt = when.get("countAllOptionsSelected")
            if isinstance(cnt, dict):
                refs.update(str(c) for c in (cnt.get("among") or []))
            for code in refs:
                _warn_for_question_code_ref(
                    code,
                    all_codes=all_codes,
                    scorable_set=scorable_set,
                    context="scoring.rules",
                    seen=seen,
                    warns=warns,
                )

    unscorable = [code for code, _u, _t in questions if code not in scorable_set]
    if unscorable:
        _append_unique(
            warns,
            seen,
            "以下题目默认不参与自动计分（答案仍正常提交）：" + ", ".join(unscorable),
        )

    return warns
