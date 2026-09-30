"""从问卷 HTML 解析题目元数据。"""

from __future__ import annotations

import re

from survey_ui_i18n import html_dict_for_locale

QuestionMeta = tuple[str, str, str]  # (code, uuid, type_num)

_SUBMIT_BTN_RE = re.compile(
    r"<button\b[^>]*\bonclick\s*=\s*[\"'][^\"']*submitSurvey\s*\(",
    re.IGNORECASE,
)
_SUBMIT_BTN_VISIBLE = '<button onclick="submitSurvey()">提交问卷</button>'
_SUBMIT_BTN_HIDDEN = (
    '<button onclick="submitSurvey()" style="display:none" aria-hidden="true">提交问卷</button>'
)


def submit_button_for_locale(locale: str | None, *, hidden: bool = False) -> str:
    """按语种生成 submitSurvey 提交按钮 HTML（壳文案随 --locale 走）。"""
    text = html_dict_for_locale(locale)["submit"]
    if hidden:
        return f'<button onclick="submitSurvey()" style="display:none" aria-hidden="true">{text}</button>'
    return f'<button onclick="submitSurvey()">{text}</button>'


def parse_questions(html: str) -> list[QuestionMeta]:
    """返回 [(code, uuid, type_num), ...]，按 DOM 出现顺序。"""
    out: list[QuestionMeta] = []
    for m in re.finditer(r"<div data-question\b[^>]*>", html):
        tag = m.group(0)
        code = (re.search(r'data-code="([^"]+)"', tag) or [None, None])[1]
        uuid = (re.search(r'data-question-uuid="([^"]+)"', tag) or [None, None])[1]
        tnum = (re.search(r'data-question-type="([^"]+)"', tag) or [None, ""])[1]
        if code:
            out.append((code, uuid or code, tnum or ""))
    return out


def ensure_default_submit_button(
    html: str, *, hidden: bool = False, locale: str | None = None
) -> str:
    """若 HTML 尚无 submitSurvey 提交钮，则在 survey 根容器内插入（考试/测评脚手架自保）。"""
    if _SUBMIT_BTN_RE.search(html):
        return html
    btn = submit_button_for_locale(locale, hidden=hidden)
    for marker in (
        "<!-- SUBMIT_ENTRY:",
        "<!-- QUESTION_INSERT_POINT:",
    ):
        idx = html.find(marker)
        if idx < 0:
            continue
        end = html.find("-->", idx)
        if end < 0:
            continue
        insert_at = end + 3
        return html[:insert_at] + "\n    " + btn + html[insert_at:]
    needle = "  </div>\n</body>"
    if needle in html:
        return html.replace(needle, f"    {btn}\n  </div>\n</body>", 1)
    return html.replace("</body>", f"    {btn}\n</body>", 1)
