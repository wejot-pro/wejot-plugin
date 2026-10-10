"""评测/考试 config 通用辅助。"""

from __future__ import annotations

import json
from pathlib import Path

from survey_ui_i18n import format_message, html_dict_for_locale


def resolve_header(config: dict, html_dir: Path) -> str:
    """开场页头图：优先 config.intro.image；否则读工作目录 header_image.txt。"""
    img = (config.get("intro") or {}).get("image")
    if img:
        return str(img).strip()
    p = html_dir / "header_image.txt"
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                return line.strip()
    return ""


def resolve_survey_title(html_dir: Path, spec_path: Path | None = None) -> str:
    """从 survey_spec.json 读取 survey.title。"""
    candidates: list[Path] = []
    if spec_path is not None:
        candidates.append(spec_path)
    candidates.append(html_dir / "survey_spec.json")
    for p in candidates:
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            title = (data.get("survey") or {}).get("title")
            if title and str(title).strip():
                return str(title).strip()
        except Exception:
            continue
    return ""


def _pick_passing_grade(grades: list) -> dict | None:
    if not grades:
        return None
    for g in grades:
        label = str(g.get("label") or "")
        if "qualified" in label:
            return g
    sorted_grades = sorted(grades, key=lambda x: x.get("min") or 0, reverse=True)
    if len(sorted_grades) >= 2:
        return sorted_grades[1]
    return sorted_grades[0] if sorted_grades else None


def _auto_exam_notices(
    *,
    total: int,
    scorable: int,
    scoring_model: str,
    max_score,
    grades: list,
    show_result: bool,
    locale: str | None = None,
) -> list[str]:
    ui = html_dict_for_locale(locale)
    notices: list[str] = []
    notices.append(format_message(ui["examNoticeTotal"], total=total))
    if scorable < total:
        notices.append(format_message(ui["examNoticeScorable"], scorable=scorable))

    if scoring_model == "sum":
        if max_score is not None:
            notices.append(format_message(ui["examNoticeFullScore"], max=max_score))
        passing = _pick_passing_grade(grades)
        if passing is not None and passing.get("min") is not None:
            label = str(passing.get("label") or ui["passingLabel"])
            notices.append(format_message(ui["examNoticePassing"], min=passing["min"], label=label))
    else:
        notices.append(ui["examNoticeRules"])
        if grades and show_result:
            notices.append(ui["examNoticeGradeResult"])

    if show_result:
        notices.append(ui["examNoticeScoreVisible"])
    else:
        if scoring_model == "rules" and not (grades and show_result):
            notices.append(ui["examNoticeCareful"])
        else:
            notices.append(ui["examNoticeThanksPage"])

    return notices


def resolve_exam_intro(
    config: dict,
    html_dir: Path,
    questions: list,
    scorable_codes: list,
    *,
    spec_path: Path | None = None,
    locale: str | None = None,
) -> tuple[dict | None, list[str], list[str]]:
    """解析考试起始页配置。

    返回 (intro_dict | None, info_messages, warn_messages)。
    intro_dict 为 None 表示 intro.enabled=false 跳过起始页。
    """
    intro_cfg = config.get("intro")
    info: list[str] = []
    warns: list[str] = []

    if intro_cfg is not None and intro_cfg.get("enabled") is False:
        return None, info, warns

    display = config.get("display") or {}
    ui = html_dict_for_locale(locale)
    scoring_cfg = config.get("scoring") or {}
    scoring_model = scoring_cfg.get("model") or "sum"
    show_result = display.get("showResultToUser", True) is not False
    total = len(questions)
    scorable = len(scorable_codes)
    grades = config.get("grades") or []
    max_score = scoring_cfg.get("maxScore")

    auto_parts: list[str] = []

    # title
    title = ""
    if intro_cfg is not None and intro_cfg.get("title"):
        title = str(intro_cfg["title"]).strip()
    if not title:
        survey_title = resolve_survey_title(html_dir, spec_path)
        if survey_title:
            title = survey_title
            auto_parts.append(f'intro.title ← survey.title「{survey_title}」')
        else:
            title = ui["examTitle"]
        warns.append("intro.title not found and survey.title could not be read from survey_spec.json; using the default 'Exam'")

    # sub
    sub = ""
    if intro_cfg is not None and intro_cfg.get("sub") is not None:
        sub = str(intro_cfg.get("sub") or "").strip()

    # notices — strategy B
    notices: list[str] = []
    notices_auto = False
    if intro_cfg is None or "notices" not in intro_cfg or intro_cfg.get("notices") is None:
        notices = _auto_exam_notices(
            total=total,
            scorable=scorable,
            scoring_model=scoring_model,
            max_score=max_score,
            grades=grades,
            show_result=show_result,
            locale=locale,
        )
        notices_auto = True
        auto_parts.append(f"intro.notices generated: {len(notices)} item(s)")
    else:
        raw = intro_cfg.get("notices")
        if isinstance(raw, list):
            notices = [str(x).strip() for x in raw if str(x).strip()]

    # chips
    chips: list[str] = []
    if intro_cfg is not None:
        raw_chips = intro_cfg.get("chips")
        if isinstance(raw_chips, list):
            chips = [str(x).strip() for x in raw_chips if str(x).strip()]

    # cta
    cta = ui["startExam"]
    if intro_cfg is not None and intro_cfg.get("cta"):
        cta = str(intro_cfg["cta"]).strip() or cta

    # image via resolve_header (needs intro in config for image key)
    header_cfg = dict(config)
    if intro_cfg is not None:
        header_cfg = {**config, "intro": intro_cfg}
    elif config.get("intro") is None:
        header_cfg = config
    image = resolve_header(header_cfg, html_dir)

    if auto_parts:
        detail = "；".join(auto_parts)
        info.append(
            f"Opening notices auto-completed: {detail} To customize, write exam_config.intro and re-run generate_exam.py."
        )
    elif intro_cfg is None:
        info.append(
            "已启用默认起始页（exam_config 未写 intro 块）。"
            "如需自定义请写入 exam_config.intro 后重跑 generate_exam.py。"
        )

    return {
        "title": title,
        "sub": sub,
        "notices": notices,
        "chips": chips,
        "cta": cta,
        "image": image,
    }, info, warns
