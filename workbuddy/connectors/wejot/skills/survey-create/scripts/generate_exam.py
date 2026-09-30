#!/usr/bin/env python3
"""考试骨架生成器（第二段，跑在 generate_free_mode_skeleton.py 之后）。

输入：已生成的自由模式骨架 + exam_config.json。
作用：注入计分/起始页/感谢页/落库链；默认 scroll 全卷展示；可选 step 逐题。
不可自动记分题型（默认 TEXTAREA/UPLOAD）不参与 eval_result，答案仍正常提交。

用法：
    python generate_exam.py --html survey-unified-generate.html --config exam_config.json

exam_config.json 结构见 references/exam_config.example.json。
"""

from __future__ import annotations

import argparse
import json
import sys
from html import escape as h
from pathlib import Path

from utils import (
    append_css_marker,
    append_js_asset,
    asset_inner_js,
    base_free_css_prefix,
    check_unscorable_warnings,
    ensure_default_submit_button,
    get_scoring_mapping,
    inject_js_to_survey_ui,
    parse_questions,
    replace_fenced_block,
    resolve_exam_intro,
    resolve_scorable_codes,
    scoring_by_uuid,
    submit_button_for_locale,
)
from survey_ui_i18n import (
    html_dict_for_locale,
    load_locale_dict_file,
    warn_if_custom_locale_needed,
)

_EXAM_PERSIST_JS = asset_inner_js("exam-persist.html")
_EXAM_CSS_BEGIN = "/* ===== 考试脚手架 CSS（generate_exam.py 注入 BEGIN） ===== */"
_EXAM_CSS_END = "/* ===== 考试脚手架 CSS（generate_exam.py 注入 END） ===== */"
_EXAM_HTML_BEGIN = "<!-- ===== 考试脚手架（generate_exam.py 注入 BEGIN） ===== -->"
_EXAM_HTML_END = "<!-- ===== 考试脚手架（generate_exam.py 注入 END） ===== -->"
_EXAM_JS_BEGIN = "/* ===== 考试脚手架·逻辑（generate_exam.py 注入 BEGIN） ===== */"
_EXAM_JS_END = "/* ===== 考试脚手架·逻辑（generate_exam.py 注入 END） ===== */"
_INJECT_MARKER = "generate_exam.py 注入"
_SURVEY_ROOT = '<div data-survey-role="survey" data-survey-mode="free">'
_SURVEY_ROOT_PENDING = '<div data-survey-role="survey" data-survey-mode="free" class="exam-survey-pending">'
# 兼容旧版注入注释（重跑时剥离）
_EXAM_HTML_BEGIN_LEGACY = "<!-- ===== 考试脚手架·起始页/感谢页/结果页（generate_exam.py 注入） ===== -->"


def _check_exam_config(config: dict, questions: list, scorable_codes: list) -> list[str]:
    warns = list(check_unscorable_warnings(config, questions, scorable_codes))
    scoring_cfg = config.get("scoring") or {}
    model = scoring_cfg.get("model") or "sum"
    code_set = {c for c, _, _ in questions}
    scorable_set = set(scorable_codes)

    if model == "sum":
        mapping = get_scoring_mapping(scoring_cfg)
        missing = [c for c in scorable_codes if c not in mapping]
        if missing:
            warns.append(f"这些可计分题在 scoring.mapping 里没有映射，将不参与计分：{', '.join(missing)}")
        for code in mapping:
            if code not in code_set:
                warns.append(f"scoring.mapping 里 {code} 在题目中不存在（拼错？）")
            else:
                for opt, sc in (mapping.get(code) or {}).items():
                    if not isinstance(sc, (int, float)):
                        warns.append(f"scoring.mapping[{code}][{opt}] 应是数字分值，当前是 {sc!r}")
    elif model == "rules":
        rules = scoring_cfg.get("rules") or []
        if not rules:
            warns.append("model=rules 但没有 rules 列表")
        has_default = any(r.get("when") == "default" for r in rules)
        if rules and not has_default:
            warns.append("rules 建议包含 when: \"default\" 兜底规则")
        for rule in rules:
            when = rule.get("when")
            if when == "default":
                continue
            if not isinstance(when, dict):
                warns.append(f"rules 条目 when 应为对象或 \"default\"，当前：{when!r}")
    else:
        warns.append(f"未知 scoring.model={model!r}，仅支持 sum / rules")

    fmt = (config.get("evalResult") or {}).get("format") or "score"
    if fmt == "grade" and not (config.get("grades") or []):
        warns.append("evalResult.format=grade but no grades tier config was provided")
    if fmt == "scoreMax" and not scoring_cfg.get("maxScore"):
        warns.append("evalResult.format=scoreMax: it is recommended to set scoring.maxScore (otherwise the script tries to infer the upper bound from the mapping)")

    return warns


def _strip_exam_html(html: str) -> str:
    """移除已注入的考试 HTML 脚手架（支持新版 fenced 与旧版注释块）。"""
    while _EXAM_HTML_BEGIN in html and _EXAM_HTML_END in html:
        html = replace_fenced_block(html, _EXAM_HTML_BEGIN, _EXAM_HTML_END, "")
    if _EXAM_HTML_BEGIN_LEGACY in html:
        start = html.index(_EXAM_HTML_BEGIN_LEGACY)
        tail = html[start:]
        if _EXAM_HTML_END in tail:
            end = start + tail.index(_EXAM_HTML_END) + len(_EXAM_HTML_END)
        else:
            end = start
            for needle in ('id="exam-next"', 'id="exam-thanks"', 'id="exam-intro"'):
                idx = tail.find(needle)
                if idx >= 0:
                    close = tail.find("\n  </div>", idx)
                    if close >= 0:
                        end = max(end, start + close + len("\n  </div>"))
        if end > start:
            html = html[:start] + html[end:]
    html = html.replace(_SURVEY_ROOT_PENDING, _SURVEY_ROOT)
    return html


def _strip_exam_js(content: str) -> str:
    """移除 survey-ui.js 中已注入的考试逻辑（含旧版无 fenced 块）。"""
    while _EXAM_JS_BEGIN in content and _EXAM_JS_END in content:
        content = replace_fenced_block(content, _EXAM_JS_BEGIN, _EXAM_JS_END, "")
    legacy_head = "/* ===== 考试脚手架·逻辑（generate_exam.py 注入）"
    idx = content.find(legacy_head)
    if idx >= 0:
        end = content.find("})();", idx)
        if end >= 0:
            end += len("})();")
            while end < len(content) and content[end] in "\n\r":
                end += 1
            content = content[:idx] + content[end:]
    return content


def _strip_exam_css(content: str) -> str:
    """移除 survey-ui.css 中已注入的考试样式（含旧版无 fenced 块）。"""
    while _EXAM_CSS_BEGIN in content and _EXAM_CSS_END in content:
        content = replace_fenced_block(content, _EXAM_CSS_BEGIN, _EXAM_CSS_END, "")
    legacy_head = "/* ===== 考试脚手架 CSS（generate_exam.py） ===== */"
    idx = content.find(legacy_head)
    if idx >= 0:
        content = content[:idx].rstrip() + "\n"
    return content


def _build_intro_block(intro: dict, *, locale: str | None = None) -> str:
    ui = html_dict_for_locale(locale)
    header_img = ""
    if intro.get("image"):
        header_img = f'<img class="exam-intro-img" src="{h(intro["image"], quote=True)}" alt="" />'
    sub_block = ""
    if intro.get("sub"):
        sub_block = f'<p class="exam-intro-sub">{h(intro["sub"])}</p>'
    notices_block = ""
    if intro.get("notices"):
        items = "".join(f"<li>{h(str(n))}</li>" for n in intro["notices"])
        notices_block = f'<ul class="exam-notices">{items}</ul>'
    chips_block = ""
    if intro.get("chips"):
        chips = "".join(f'<span class="exam-chip">{h(str(c))}</span>' for c in intro["chips"])
        chips_block = f'<div class="exam-chips">{chips}</div>'
    cta = h(str(intro.get("cta") or ui["startExam"]))
    return f"""
  <div id="exam-intro" class="exam-layer" style="display:none">
    <div class="exam-card exam-intro-card">
      {header_img}
      <h1 class="exam-intro-title">{h(intro.get("title") or ui["examTitle"])}</h1>
      {sub_block}
      {notices_block}
      {chips_block}
      <button id="exam-start" type="button" class="exam-btn-primary">{cta}</button>
    </div>
  </div>"""


def _build_overlays(config: dict, intro: dict | None, *, locale: str | None = None) -> str:
    ui = html_dict_for_locale(locale)
    display = config.get("display") or {}
    thanks = h(str(display.get("thanksText") or ui["thanksDefault"]))
    show_result = display.get("showResultToUser", True) is not False
    intro_block = _build_intro_block(intro, locale=locale) if intro else ""
    result_block = ""
    if show_result:
        result_block = f"""
  <div id="exam-result" class="exam-layer" style="display:none">
    <div class="exam-card">
      <h1 id="exam-result-title" class="exam-result-title">{ui["examResultTitle"]}</h1>
      <div id="exam-result-score" class="exam-result-score"></div>
      <p id="exam-result-desc" class="exam-result-desc"></p>
    </div>
  </div>"""
    step_next = ""
    if (display.get("layout") or "scroll") == "step":
        step_next = f'\n  <div id="exam-next"><button type="button">{ui["nextQuestion"]}</button></div>'
    return f"""
  {_EXAM_HTML_BEGIN}
{intro_block}{result_block}
  <div id="exam-thanks" class="exam-layer" style="display:none">
    <div class="exam-card">
      <h1 class="exam-thanks-title">{ui["submitted"]}</h1>
      <p class="exam-thanks-text">{thanks}</p>
    </div>
  </div>{step_next}
  {_EXAM_HTML_END}
"""


def _build_exam_css(layout: str, intro_enabled: bool) -> str:
    common = f"""{_EXAM_CSS_BEGIN}
.exam-layer {{ position: fixed; inset: 0; z-index: 80; display: none; align-items: center; justify-content: center;
  background: rgba(245,246,248,.96); padding: 24px 16px; overflow-y: auto; }}
.exam-layer[style*="flex"], .exam-layer.exam-show {{ display: flex !important; }}
.exam-card {{ background: #fff; border-radius: 16px; padding: 28px 24px; max-width: 420px; width: 100%;
  box-shadow: 0 8px 32px rgba(0,0,0,.08); text-align: center; }}
.exam-thanks-title, .exam-result-title, .exam-intro-title {{ margin: 0 0 12px; font-size: 22px; color: #1f2329; }}
.exam-thanks-text, .exam-result-desc, .exam-intro-sub {{ margin: 0; color: #646a73; line-height: 1.7; font-size: 15px; }}
.exam-result-score {{ font-size: 28px; font-weight: 700; color: #2b59d6; margin: 8px 0 12px; }}
.exam-intro-img {{ width: 100%; max-width: 320px; border-radius: 16px; margin: 0 auto 18px; display: block;
  box-shadow: 0 6px 20px rgba(0,0,0,.1); }}
.exam-notices {{ text-align: left; margin: 16px 0; padding-left: 20px; color: #4a5159; font-size: 14px; line-height: 1.8; }}
.exam-notices li {{ margin: 4px 0; }}
.exam-chips {{ display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin: 16px 0; }}
.exam-chip {{ padding: 6px 12px; background: #f0f3f8; border-radius: 999px; font-size: 13px; color: #3a4250; }}
.exam-btn-primary {{ display: inline-block; margin-top: 8px; padding: 14px 28px; border: 0; border-radius: 12px;
  background: #5b8cff; color: #fff; font-size: 16px; font-weight: 600; cursor: pointer; }}
"""
    pending_css = ""
    if intro_enabled and layout == "scroll":
        pending_css = """
.exam-survey-pending [data-question],
.exam-survey-pending button[onclick*="submitSurvey"] { display: none !important; }
"""
    step_css = """
[data-survey-role="survey"] { min-height: 100vh; display: flex; flex-direction: column; justify-content: center; padding-bottom: 96px; }
[data-survey-role="survey"] [data-question] { display: none; }
[data-survey-role="survey"] [data-question].active { display: block; width: 100%; min-width: 0; }
#exam-next { position: fixed; left: 0; right: 0; bottom: 0; z-index: 50; display: none; justify-content: center;
  padding: 12px 16px calc(12px + env(safe-area-inset-bottom)); background: #fff; box-shadow: 0 -4px 16px rgba(0,0,0,.06); }
#exam-next > button { width: 100%; max-width: 360px; padding: 15px; border: 0; border-radius: 12px;
  background: #5b8cff; color: #fff; font-size: 16px; font-weight: 600; cursor: pointer; }
"""
    scroll_css = """
[data-survey-role="survey"] [data-question] { display: block !important; }
"""
    body = (common + pending_css + (step_css if layout == "step" else scroll_css)).rstrip()
    return body + f"\n{_EXAM_CSS_END}\n"


def _build_js(config: dict, code2uuid: dict, scorable_codes: list, *, intro_enabled: bool) -> str:
    display = config.get("display") or {}
    scoring_cfg = config.get("scoring") or {}
    model = scoring_cfg.get("model") or "sum"
    layout = display.get("layout") or "scroll"
    scorable_uuids = [code2uuid[c] for c in scorable_codes if c in code2uuid]

    cfg = {
        "layout": layout,
        "introEnabled": intro_enabled,
        "showResultToUser": display.get("showResultToUser", True) is not False,
        "scoringModel": model,
        "mapping": scoring_by_uuid(get_scoring_mapping(scoring_cfg), code2uuid),
        "rules": scoring_cfg.get("rules") or [],
        "scorableUuids": scorable_uuids,
        "code2uuid": code2uuid,
        "grades": config.get("grades") or [],
        "evalResult": config.get("evalResult") or {"format": "score"},
        "maxScore": scoring_cfg.get("maxScore"),
    }
    cfg_json = json.dumps(cfg, ensure_ascii=False)
    body = """
    (function () {
      var EXAM = __EXAM_CONFIG__;
      function byId(id) { return document.getElementById(id); }
      function setText(id, v) { var e = byId(id); if (e) e.textContent = v == null ? '' : v; }
      function showLayer(id) {
        var el = byId(id); if (!el) return;
        el.style.display = 'flex';
        el.classList.add('exam-show');
      }
      var questions = Array.prototype.slice.call(document.querySelectorAll('[data-survey-role="survey"] [data-question]'));
      var scorableSet = {};
      (EXAM.scorableUuids || []).forEach(function (u) { scorableSet[u] = true; });
      var cur = 0;
      var surveyRoot = document.querySelector('[data-survey-role="survey"]');

      function byUuid(u) {
        for (var i = 0; i < questions.length; i++) if (questions[i].dataset.questionUuid === u) return questions[i];
        return null;
      }
      function byCode(c) { return byUuid(EXAM.code2uuid[c]); }
      function selVal(q) {
        var a = state.answers[q.dataset.questionUuid];
        if (q.getAttribute('data-question-type') === '9') {
          if (!Array.isArray(a)) return null;
          return a.map(function (x) { return x && x.value; }).filter(function (v) { return v != null; });
        }
        return (a && a[0]) ? a[0].value : null;
      }
      function optionCount(q) { return q.querySelectorAll('[data-option]').length; }
      function allOptionsSelected(q) {
        var v = selVal(q), n = optionCount(q);
        return Array.isArray(v) && n > 0 && v.length >= n;
      }
      function noneSelected(q) {
        var v = selVal(q);
        if (Array.isArray(v)) return v.length === 0;
        return v == null || v === '';
      }
      function answered(q) {
        if (window.WJFreeValidation && WJFreeValidation.questionSatisfied) {
          return WJFreeValidation.questionSatisfied(q);
        }
        var a = state.answers[q.dataset.questionUuid], t = q.getAttribute('data-question-type');
        if (t === '8' || t === '9' || t === '15') return Array.isArray(a) && a.length > 0;
        if (t === '1') return typeof a === 'string' && a.trim() !== '';
        if (t === '10') return typeof a === 'number' && !Number.isNaN(a);
        if (t === '28') return Array.isArray(a) && a.some(function (x) { return x && x.rowTitle; });
        return a != null;
      }

      function computeSum() {
        var total = 0;
        Object.keys(EXAM.mapping || {}).forEach(function (u) {
          if (!scorableSet[u]) return;
          var q = byUuid(u); if (!q) return;
          var v = selVal(q), m = EXAM.mapping[u];
          if (Array.isArray(v)) return;
          if (v != null && m && m[v] != null) total += Number(m[v]) || 0;
        });
        return total;
      }
      function matchWhen(when) {
        if (when === 'default') return true;
        if (!when || typeof when !== 'object') return false;
        var list, q, i, cnt;
        if (when.everyAllOptionsSelected) {
          list = when.everyAllOptionsSelected;
          for (i = 0; i < list.length; i++) {
            q = byCode(list[i]); if (!q || !allOptionsSelected(q)) return false;
          }
        }
        if (when.everyNoneSelected) {
          list = when.everyNoneSelected;
          for (i = 0; i < list.length; i++) {
            q = byCode(list[i]); if (!q || !noneSelected(q)) return false;
          }
        }
        if (when.countAllOptionsSelected) {
          cnt = 0;
          list = when.countAllOptionsSelected.among || [];
          for (i = 0; i < list.length; i++) {
            q = byCode(list[i]); if (q && allOptionsSelected(q)) cnt++;
          }
          if (cnt !== Number(when.countAllOptionsSelected.equals)) return false;
        }
        return true;
      }
      function computeRules() {
        var rules = EXAM.rules || [];
        for (var i = 0; i < rules.length; i++) {
          if (matchWhen(rules[i].when)) return Number(rules[i].score) || 0;
        }
        return 0;
      }
      function computeScore() {
        if (EXAM.scoringModel === 'rules') return computeRules();
        return computeSum();
      }
      function inferMaxScore() {
        if (EXAM.maxScore != null) return Number(EXAM.maxScore) || 0;
        var max = 0;
        Object.keys(EXAM.mapping || {}).forEach(function (u) {
          if (!scorableSet[u]) return;
          var m = EXAM.mapping[u], best = 0;
          Object.keys(m || {}).forEach(function (k) { best = Math.max(best, Number(m[k]) || 0); });
          max += best;
        });
        return max;
      }
      function pickGrade(score) {
        var grades = (EXAM.grades || []).slice().sort(function (a, b) { return (b.min || 0) - (a.min || 0); });
        for (var i = 0; i < grades.length; i++) {
          if (score >= Number(grades[i].min || 0)) return grades[i].label || '';
        }
        return grades.length ? (grades[grades.length - 1].label || '') : String(score);
      }
      function formatEvalResult(score) {
        var fmt = (EXAM.evalResult && EXAM.evalResult.format) || 'score';
        if (fmt === 'grade') return pickGrade(score);
        if (fmt === 'scoreMax') return String(score) + '/' + String(inferMaxScore());
        return String(score);
      }
      function renderResult(score) {
        var fmt = (EXAM.evalResult && EXAM.evalResult.format) || 'score';
        if (fmt === 'grade') {
          setText('exam-result-score', pickGrade(score));
          setText('exam-result-desc', _suiT('yourGrade'));
        } else {
          setText('exam-result-score', String(score));
          setText('exam-result-desc', EXAM.maxScore != null ? (_suiT('fullScore') + ' ' + EXAM.maxScore) : '');
        }
      }
      function finishExam() {
        if (window.WJFreeValidation) {
          var vAll = WJFreeValidation.validateAll({ toast: true });
          if (!vAll.ok) return;
        }
        var score = computeScore();
        window.__WJ_EVAL_RESULT__ = formatEvalResult(score);
        if (EXAM.showResultToUser) {
          renderResult(score);
          showLayer('exam-result');
        } else {
          showLayer('exam-thanks');
        }
        if (window.WJExamPersist && typeof window.WJExamPersist.finish === 'function') {
          window.WJExamPersist.finish();
        }
      }

      var showQ = null;
      if (EXAM.layout === 'step') {
        function syncNextBtn() {
          var nb = byId('exam-next'); if (!nb) return;
          var last = cur >= questions.length - 1;
          var btn = nb.querySelector('button');
          if (btn) btn.textContent = last ? _suiT('submit') : _suiT('nextQuestion');
          nb.style.display = (last && !answered(questions[cur])) ? 'none' : 'flex';
        }
        showQ = function (idx) {
          questions.forEach(function (q, i) { q.classList.toggle('active', i === idx); });
          cur = idx; window.scrollTo(0, 0);
          syncNextBtn();
        };
        function nextStep() {
          if (window.WJFreeValidation) {
            var v = WJFreeValidation.validateQuestion(questions[cur], { toast: true });
            if (!v.ok) return;
          } else if (!answered(questions[cur])) { alert(_suiT('completeQuestionFirst')); return; }
          if (cur < questions.length - 1) showQ(cur + 1); else finishExam();
        }
        questions.forEach(function (q, idx) {
          if (q.getAttribute('data-question-type') !== '8') return;
          q.querySelectorAll('[data-option]').forEach(function (opt) {
            opt.addEventListener('click', function () { setTimeout(function () { if (cur === idx) nextStep(); }, 280); });
          });
        });
        if (surveyRoot) ['click', 'input', 'change'].forEach(function (ev) {
          surveyRoot.addEventListener(ev, function () { setTimeout(syncNextBtn, 0); });
        });
        var nb = byId('exam-next');
        if (nb) nb.querySelector('button').addEventListener('click', nextStep);
        var submitBtn = document.querySelector('[data-survey-role="survey"] button[onclick*="submitSurvey"]');
        if (submitBtn) submitBtn.style.display = 'none';
      } else {
        window.submitSurvey = function () { finishExam(); return false; };
        var submitBtn = document.querySelector('[data-survey-role="survey"] button[onclick*="submitSurvey"]');
        if (submitBtn) {
          submitBtn.onclick = function (e) { e && e.preventDefault(); finishExam(); return false; };
        }
      }

      function startExam() {
        var intro = byId('exam-intro');
        if (intro) intro.style.display = 'none';
        if (surveyRoot) surveyRoot.classList.remove('exam-survey-pending');
        if (EXAM.layout === 'step' && showQ) showQ(0);
      }

      function wireIntro() {
        if (!EXAM.introEnabled) {
          if (EXAM.layout === 'step' && showQ) showQ(0);
          return;
        }
        if (surveyRoot) surveyRoot.classList.add('exam-survey-pending');
        var intro = byId('exam-intro');
        if (intro) intro.style.display = 'flex';
        var startBtn = byId('exam-start');
        if (startBtn) startBtn.addEventListener('click', startExam);
      }

      if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wireIntro);
      else wireIntro();
    })();
""".replace("__EXAM_CONFIG__", cfg_json)
    return f"{_EXAM_JS_BEGIN}\n{body.rstrip()}\n{_EXAM_JS_END}\n"


def apply_exam(
    html: str,
    config: dict,
    html_dir: Path,
    *,
    spec_path: Path | None = None,
    locale: str | None = None,
):
    questions = parse_questions(html)
    if not questions:
        raise ValueError("骨架里没找到 [data-question]，确认先跑了 generate_free_mode_skeleton.py")
    code2uuid = {c: u for c, u, _ in questions}
    scorable_codes = resolve_scorable_codes(config, questions)
    display = config.get("display") or {}
    layout = display.get("layout") or "scroll"

    intro, intro_info, intro_warns = resolve_exam_intro(
        config, html_dir, questions, scorable_codes, spec_path=spec_path, locale=locale
    )
    intro_enabled = intro is not None

    warns = _check_exam_config(config, questions, scorable_codes) + intro_warns
    overlays = _build_overlays(config, intro, locale=locale)
    js = _build_js(config, code2uuid, scorable_codes, intro_enabled=intro_enabled)

    html = _strip_exam_html(html)

    js_path = html_dir / "survey-ui.js"
    if js_path.is_file():
        js_path.write_text(_strip_exam_js(js_path.read_text(encoding="utf-8")), encoding="utf-8")

    css_path = html_dir / "survey-ui.css"
    if css_path.is_file():
        css_path.write_text(_strip_exam_css(css_path.read_text(encoding="utf-8")), encoding="utf-8")

    if intro_enabled and layout == "scroll" and _SURVEY_ROOT in html:
        html = html.replace(_SURVEY_ROOT, _SURVEY_ROOT_PENDING, 1)

    # free 骨架默认不再带提交钮；考试 scroll 布局依赖该按钮接 finishExam
    html = ensure_default_submit_button(html, hidden=False, locale=locale)

    submit_btn = submit_button_for_locale(locale)
    if submit_btn in html:
        html = html.replace(submit_btn + "\n  </div>", submit_btn + "\n  </div>\n" + overlays, 1)
    elif _EXAM_HTML_BEGIN not in html:
        html = html.replace("  </div>\n</body>", "  </div>\n" + overlays + "\n</body>", 1)
        if _EXAM_HTML_BEGIN not in html:
            html = html.replace("</body>", overlays + "\n</body>", 1)

    html = inject_js_to_survey_ui(
        html_dir,
        js,
        html,
        marker=_INJECT_MARKER,
        replace=True,
        block_begin=_EXAM_JS_BEGIN,
        block_end=_EXAM_JS_END,
    )

    css_path = html_dir / "survey-ui.css"
    prefix = base_free_css_prefix(css_path.read_text(encoding="utf-8") if css_path.is_file() else "")
    append_css_marker(
        html_dir,
        _EXAM_CSS_BEGIN,
        _build_exam_css(layout, intro_enabled),
        prefix=prefix,
        replace=True,
        block_end=_EXAM_CSS_END,
    )
    append_js_asset(html_dir, _EXAM_PERSIST_JS, fence_marker="EXAM_PERSIST BEGIN")

    return html, warns, intro_info, intro_enabled


def main() -> int:
    ap = argparse.ArgumentParser(description="考试骨架生成器（跑在 free 骨架之后）")
    ap.add_argument("--html", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--spec", default=None, help="survey_spec.json 路径（默认 html 同目录下 survey_spec.json）")
    ap.add_argument("--locale", default=None, help="问卷回答端 UI 文案语种（如 zh-CN / en-US / es-MX）")
    ap.add_argument(
        "--i18n-dict",
        default=None,
        help="额外语种字典 JSON（{locale: {key: value}}），用于主字典未覆盖的语种（如韩语 ko）；key 清单与示例见 references/i18n-dict.example.json",
    )
    args = ap.parse_args()

    if args.i18n_dict:
        load_locale_dict_file(args.i18n_dict)
    warn_if_custom_locale_needed(args.locale, args.i18n_dict)

    html_path, cfg_path = Path(args.html), Path(args.config)
    spec_path = Path(args.spec) if args.spec else None
    if not html_path.is_file():
        print(f"❌ HTML does not exist: {html_path}")
        return 1
    if not cfg_path.is_file():
        print(f"❌ config does not exist: {cfg_path}")
        return 1
    try:
        config = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ Failed to parse exam_config.json: {e}")
        return 1

    try:
        out, warns, intro_info, intro_enabled = apply_exam(
            html_path.read_text(encoding="utf-8"),
            config,
            html_path.parent,
            spec_path=spec_path,
            locale=args.locale,
        )
    except Exception as e:
        print(f"❌ Injection failed: {e}")
        return 1

    html_path.write_text(out, encoding="utf-8")
    nq = len(parse_questions(out))
    layout = (config.get("display") or {}).get("layout") or "scroll"
    intro_msg = "已注入考试起始页" if intro_enabled else "intro.enabled=false，跳过起始页"
    print(f"✅ Exam scaffolding injected (layout={layout}, {nq} question(s), {intro_msg}). Persistence is handled by the EXAM_PERSIST suite automatically.")
    if intro_info:
        for msg in intro_info:
            print(f"ℹ️ {msg}")
    if warns:
        print(f"⚠️ Config self-check found {len(warns)} hint(s) (non-blocking):")
        for w in warns:
            print("   - " + w)
    print("   Next: verify start page → answering → submit → thank-you page in the browser; check eval_result in the backend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
