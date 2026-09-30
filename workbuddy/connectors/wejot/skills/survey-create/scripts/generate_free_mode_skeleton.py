#!/usr/bin/env python3
"""自由模式骨架生成器。

接受 survey_spec.json（统一 questions 数组格式），内部自动转换成分类数组格式，
并生成：
- question_schema_generate.json（分类数组格式）
- survey-unified-generate.html（最小化 HTML 骨架）

用法：
    python generate_free_mode_skeleton.py \
      --spec /path/to/survey_spec.json \
      --output /path/to/survey-unified-generate.html
"""

from __future__ import annotations

import argparse
import json
import re
from html import escape as html_escape
from pathlib import Path
from typing import Any, Dict, List

from utils.checkbox_choices import checkbox_option_count, normalize_checkbox_choices
from survey_ui_i18n import (
    DEFAULT_LOCALE,
    free_mode_i18n_prelude,
    html_dict_for_locale,
    load_locale_dict_file,
    resolve_locale,
    warn_if_custom_locale_needed,
)

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def _read_asset(name: str) -> str:
    """读取与脚本同目录 assets/ 下的静态资源（基座样式 / 守卫脚本等，解耦出 .py 便于维护）。
    资源缺失时返回空串而非抛错——宁可降级为"无该资源"，也不让整条骨架生成因缺文件而崩溃。"""
    try:
        return (_ASSETS_DIR / name).read_text(encoding="utf-8")
    except Exception:
        return ""


def _asset_inner_js(name: str) -> str:
    """读取 assets/ 下被 <script>…</script> 包裹的资源，剥掉外壳返回纯 JS（用于嵌入 survey-ui.js）。"""
    raw = _read_asset(name)
    m = re.search(r"<script[^>]*>(.*)</script>", raw, re.DOTALL | re.IGNORECASE)
    return (m.group(1) if m else raw).strip()

QUESTION_ARRAY_KEYS = [
    "radioQuestions",
    "checkboxQuestions",
    "textQuestions",
    "uploadQuestions",
    "scaleQuestions",
    "matrixScaleQuestions",
    "genericQuestions",
]

SURVEY_BRIDGE_URL = "https://wejot-pro.oss-cn-shenzhen.aliyuncs.com/jscript/_agent_uploads/survey-bridge-20260823-1.js"

# 支持字符串枚举与数值型 type 码的互转
_TYPE_NORMALIZE_MAP = {
    # 字符串枚举
    "RADIO": "RADIO",
    "CHECKBOX": "CHECKBOX",
    "TEXTAREA": "TEXTAREA",
    "UPLOAD": "UPLOAD",
    "SCALE": "SCALE",
    "MATRIX_SCALE": "MATRIX_SCALE",
    "GENERIC": "GENERIC",
    # 数值型（常见于自由模式手写 JSON）
    1: "RADIO",
    2: "CHECKBOX",
    3: "TEXTAREA",
    # 字符串型数值（兜底）
    "1": "RADIO",
    "2": "CHECKBOX",
    "3": "TEXTAREA",
}


def _normalize_type(qtype: Any) -> str:
    """将各种 type 表示统一为字符串枚举。"""
    if qtype in _TYPE_NORMALIZE_MAP:
        return _TYPE_NORMALIZE_MAP[qtype]
    # 若本身就是目标字符串则原样返回
    if isinstance(qtype, str) and qtype.upper() in _TYPE_NORMALIZE_MAP:
        return qtype.upper()
    return str(qtype) if qtype is not None else ""


def _extract_questions(schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 schema 提取所有题目，按 sort 排序。"""
    out: List[Dict[str, Any]] = []
    for key in QUESTION_ARRAY_KEYS:
        out.extend(schema.get(key, []))
    out.sort(key=lambda q: q.get("sort", 0))
    return out


def _extract_text(val: Any) -> str:
    """从字符串或 dict 中提取可显示文本（兼容 label/title/rowTitle 键）。"""
    if isinstance(val, dict):
        return str(val.get("label") or val.get("title") or val.get("rowTitle") or "")
    return str(val)


# 与 survey-bridge.js QUESTION_TYPES 保持一致，供 collectSurveyData() 识别题型
_TYPE_NUM_MAP = {
    "RADIO": 8,
    "CHECKBOX": 9,
    "TEXTAREA": 1,
    "SCALE": 10,
    "UPLOAD": 15,
    "MATRIX_SCALE": 28,
    "GENERIC": 39,
}


def _desc_html(q: Dict[str, Any]) -> str:
    desc = q.get("description", "")
    return f'      <div class="qd">{html_escape(desc, quote=False)}</div>\n' if desc else ""


def _build_question_html(
    q: Dict[str, Any],
    idx: int,
    page_by_code: Dict[str, int] | None = None,
    locale: str = DEFAULT_LOCALE,
) -> str:
    """根据题型生成单道题的基础 DOM。"""
    qtype = _normalize_type(q.get("type", ""))
    code = q["code"]
    uuid = q.get("uuid", "")
    title = q["title"]
    req = q.get("required", 0)
    page = (page_by_code or {}).get(code, q.get("page", 1))
    req_attr = f' data-required="{req}"'
    uuid_attr = f' data-question-uuid="{uuid}"' if uuid else ""
    type_num = _TYPE_NUM_MAP.get(qtype, "")
    type_attr = f' data-question-type="{type_num}"' if type_num else ""
    index_attr = f' data-question-index="{idx}"'
    page_attr = f' data-page="{page}"'

    body: str
    if qtype == "RADIO":
        body = _build_radio_checkbox(q, idx, is_radio=True, req_attr=req_attr, uuid_attr=uuid_attr, type_attr=type_attr, index_attr=index_attr, page_attr=page_attr)
    elif qtype == "CHECKBOX":
        body = _build_radio_checkbox(q, idx, is_radio=False, req_attr=req_attr, uuid_attr=uuid_attr, type_attr=type_attr, index_attr=index_attr, page_attr=page_attr)
    elif qtype == "TEXTAREA":
        body = _build_textarea(q, idx, req_attr=req_attr, uuid_attr=uuid_attr, type_attr=type_attr, index_attr=index_attr, page_attr=page_attr, locale=locale)
    elif qtype == "SCALE":
        body = _build_scale(q, idx, req_attr=req_attr, uuid_attr=uuid_attr, type_attr=type_attr, index_attr=index_attr, page_attr=page_attr)
    elif qtype == "MATRIX_SCALE":
        body = _build_matrix(q, idx, req_attr=req_attr, uuid_attr=uuid_attr, type_attr=type_attr, index_attr=index_attr, page_attr=page_attr)
    elif qtype == "UPLOAD":
        body = _build_upload(q, idx, req_attr=req_attr, uuid_attr=uuid_attr, type_attr=type_attr, index_attr=index_attr, page_attr=page_attr, locale=locale)
    elif qtype == "GENERIC":
        body = _build_generic(q, idx, req_attr=req_attr, uuid_attr=uuid_attr, type_attr=type_attr, index_attr=index_attr, page_attr=page_attr)
    else:
        # 未知题型兜底：保留 data-question 结构，方便编辑器识别
        body = f'''    <!-- Question {idx}: {code} (unknown question type {qtype}) -->
    <div data-question{type_attr}{index_attr} data-code="{code}"{uuid_attr}{req_attr}{page_attr}>
      <b data-q-number>{idx:02d}</b>
      <h2 data-title>{html_escape(title, quote=False)}</h2>
{_desc_html(q)}      <div style="color:#c00">【Unknown question type: {html_escape(str(qtype), quote=False)}】</div>
    </div>'''

    region_start = f'<!-- QUESTION_REGION_START: index={idx} type={type_num} title="{code}" page={page} -->'
    region_end = f'<!-- QUESTION_REGION_END: index={idx} -->'
    return f'    {region_start}\n{body}\n    {region_end}'


def _build_radio_checkbox(q: Dict[str, Any], idx: int, is_radio: bool, req_attr: str, uuid_attr: str, type_attr: str, index_attr: str, page_attr: str) -> str:
    code = q["code"]
    title = q["title"]
    options = q.get("options", [])
    extra = ""
    if not is_radio:
        other_on = int(q.get("otherEnabled", 0) or 0) == 1
        opt_count = checkbox_option_count(options, other_enabled=other_on)
        min_c, max_c = normalize_checkbox_choices(
            q.get("minChoices"), q.get("maxChoices"), option_count=opt_count
        )
        extra = f' data-min-choices="{min_c}" data-max-choices="{max_c}"'

    if is_radio:
        opts = "\n      ".join(
            f'<div data-option data-option-value="{html_escape(str(i+1), quote=True)}">{html_escape(_extract_text(opt), quote=False)}</div>'
            for i, opt in enumerate(options)
        )
    else:
        # 多选用原生 <input type="checkbox">：选中态归浏览器持有，事件 handler 只读 :checked。
        # 这样即便被多处绑定也幂等（不会出现两个 toggle 相互抵消导致"点了选不动"）。
        opts = "\n      ".join(
            f'<label data-option data-option-value="{html_escape(str(i+1), quote=True)}">'
            f'<input type="checkbox" data-option-input>'
            f'<span data-option-text>{html_escape(_extract_text(opt), quote=False)}</span></label>'
            for i, opt in enumerate(options)
        )

    return f'''    <!-- Question {idx}: {code} -->
    <div data-question{type_attr}{index_attr} data-code="{code}"{uuid_attr}{req_attr}{page_attr}{extra}>
      <b data-q-number>{idx:02d}</b>
      <h2 data-title>{html_escape(title, quote=False)}</h2>
{_desc_html(q)}      {opts}
    </div>'''


def _build_textarea(
    q: Dict[str, Any],
    idx: int,
    req_attr: str,
    uuid_attr: str,
    type_attr: str,
    index_attr: str,
    page_attr: str,
    locale: str = DEFAULT_LOCALE,
) -> str:
    code = q["code"]
    title = q["title"]
    placeholder = q.get("placeholder") or html_dict_for_locale(locale)["placeholder"]
    min_len = q.get("minLength", 0)
    max_len = q.get("maxLength", 255)

    return f'''    <!-- Question {idx}: {code} -->
    <div data-question{type_attr}{index_attr} data-code="{code}"{uuid_attr}{req_attr}{page_attr} data-min-length="{min_len}" data-max-length="{max_len}">
      <b data-q-number>{idx:02d}</b>
      <h2 data-title>{html_escape(title, quote=False)}</h2>
{_desc_html(q)}      <textarea placeholder="{html_escape(placeholder, quote=True)}" data-input-type="text" rows="4"></textarea>
    </div>'''


def _build_scale(q: Dict[str, Any], idx: int, req_attr: str, uuid_attr: str, type_attr: str, index_attr: str, page_attr: str) -> str:
    code = q["code"]
    title = q["title"]
    min_scale = q.get("minScale", 1)
    max_scale = q.get("maxScale", 5)

    items = " ".join(
        f'<span data-scale-value="{i}">{i}</span>'
        for i in range(min_scale, max_scale + 1)
    )

    scale_labels = q.get("scaleLabels")
    sl_html = ""
    if scale_labels:
        left = html_escape(str(scale_labels.get("left", "")), quote=False)
        right = html_escape(str(scale_labels.get("right", "")), quote=False)
        sl_html = f'\n      <div class="sl"><span>{left}</span><span>{right}</span></div>'

    return f'''    <!-- Question {idx}: {code} -->
    <div data-question{type_attr}{index_attr} data-code="{code}"{uuid_attr}{req_attr}{page_attr}>
      <b data-q-number>{idx:02d}</b>
      <h2 data-title>{html_escape(title, quote=False)}</h2>
{_desc_html(q)}      <div data-survey-role="scale-group">
        {items}
      </div>{sl_html}
    </div>'''


def _build_matrix(q: Dict[str, Any], idx: int, req_attr: str, uuid_attr: str, type_attr: str, index_attr: str, page_attr: str) -> str:
    code = q["code"]
    title = q["title"]
    rows = q.get("rows", [])
    # 列定义：spec 草稿用 matrixColumns；question_schema_generate.json 用 columns
    cols = q.get("matrixColumns") or q.get("columns") or []
    if not cols:
        cols = [{"title": str(i), "score": i, "sort": i} for i in range(1, 6)]

    # 列文案兼容 columnTitle（schema anyOf 允许 columnTitle/title）；都缺才回退索引号。
    col_items = " ".join(
        f'<span data-scale-value="{c.get("score", i+1)}">{html_escape(str(c.get("title") or c.get("columnTitle") or (i + 1)), quote=False)}</span>'
        for i, c in enumerate(cols)
    )

    row_html = "\n        ".join(
        f'<div data-survey-role="matrix-row" data-matrix-row="{html_escape(_extract_text(r), quote=True)}" data-matrix-row-label="{html_escape(_extract_text(r), quote=True)}">'
        f'<span>{html_escape(_extract_text(r), quote=False)}</span>'
        f'<div data-survey-role="matrix-values">{col_items}</div></div>'
        for r in rows
    )

    return f'''    <!-- Question {idx}: {code} -->
    <div data-question{type_attr}{index_attr} data-code="{code}"{uuid_attr}{req_attr}{page_attr}>
      <b data-q-number>{idx:02d}</b>
      <h2 data-title>{html_escape(title, quote=False)}</h2>
{_desc_html(q)}      <div data-survey-role="matrix-group">
        {row_html}
      </div>
    </div>'''


def _build_upload(
    q: Dict[str, Any],
    idx: int,
    req_attr: str,
    uuid_attr: str,
    type_attr: str,
    index_attr: str,
    page_attr: str,
    locale: str = DEFAULT_LOCALE,
) -> str:
    code = q["code"]
    title = q["title"]
    # Preserve the positive per-question limits produced by the standard generator.
    max_count = q.get("maxFileCount", 1)
    max_size = q.get("maxFileSize", 102400)
    # fileTypes 为无点扩展名（给 Java 入库）；HTML accept 需带点的 Web 形式。
    file_types = q.get("fileTypes") or []
    accept_value = ",".join("." + e for e in file_types)
    accept_attr = f' accept="{accept_value}"' if accept_value else ""

    return f'''    <!-- Question {idx}: {code} -->
    <div data-question{type_attr}{index_attr} data-code="{code}"{uuid_attr}{req_attr}{page_attr} data-max-file-count="{max_count}" data-max-file-size="{max_size}">
      <b data-q-number>{idx:02d}</b>
      <h2 data-title>{html_escape(title, quote=False)}</h2>
{_desc_html(q)}      <label class="upload-area">
        <input type="file"{accept_attr} />
        <span>{html_dict_for_locale(locale)["clickToUpload"]}</span>
      </label>
    </div>'''


def _build_generic(q: Dict[str, Any], idx: int, req_attr: str, uuid_attr: str, type_attr: str, index_attr: str, page_attr: str) -> str:
    code = q["code"]
    title = q["title"]
    generic_style = q.get("genericStyle", "")
    generic_html = q.get("genericHtml", "")
    generic_script = q.get("genericScript", "")
    answer_keys = ",".join(q.get("answerKeys", ["answer"]))

    return f'''    <!-- 第{idx}题：{code}（GENERIC） -->
    <div data-question{type_attr}{index_attr} data-code="{code}"{uuid_attr}{req_attr}{page_attr}>
      <b data-q-number>{idx:02d}</b>
      <h2 data-title>{html_escape(title, quote=False)}</h2>
{_desc_html(q)}      <div data-survey-role="generic-container">
        <style>
{generic_style}
        </style>
        <div class="gc">
{generic_html}
        </div>
        <script data-answer-keys="{answer_keys}">
          (function () {{
            // 自包含底座：脚本自行定位容器与题目 UUID，不依赖模板注入。
            // genericScript 仍按规范使用 wrapper / questionId / submitAnswer。
            var __sc = document.currentScript;
            var wrapper = __sc && __sc.closest('[data-survey-role="generic-container"]');
            var __q = wrapper && wrapper.closest('[data-question][data-question-uuid]');
            var questionId = __q ? __q.getAttribute('data-question-uuid') : null;
            // 与 region 等组件一致，统一通过全局 window.submitGenericAnswer 上报；
            // 自由模式底座已包装该全局，会把答案镜像写入 state.answers。
            function submitAnswer(obj) {{
              if (!questionId || !obj || typeof obj !== 'object' || !Object.keys(obj).length) return;
              if (typeof window.submitGenericAnswer === 'function') window.submitGenericAnswer(questionId, obj);
            }}
            try {{
{generic_script}
            }} catch (e) {{ console.error(e); }}
          }})();
        </script>
      </div>
    </div>'''


def _build_js_answer_entry(q: Dict[str, Any]) -> str:
    """生成 buildAnswers 中每道题的 entry。"""
    code = q["code"]
    uuid = q.get("uuid", code)
    qtype = _normalize_type(q.get("type", ""))

    if qtype == "RADIO":
        return f"      {{ data: {{ questionUuid: '{uuid}', questionType: 'RADIO', options: state.answers['{uuid}'] || [] }} }}"
    if qtype == "CHECKBOX":
        return f"      {{ data: {{ questionUuid: '{uuid}', questionType: 'CHECKBOX', options: state.answers['{uuid}'] || [] }} }}"
    if qtype == "TEXTAREA":
        return f"      {{ data: {{ questionUuid: '{uuid}', questionType: 'TEXTAREA', value: state.answers['{uuid}'] || '', textId: null }} }}"
    if qtype == "SCALE":
        return f"      {{ data: {{ questionUuid: '{uuid}', questionType: 'SCALE', score: state.answers['{uuid}'] || 0, scaleId: null }} }}"
    if qtype == "MATRIX_SCALE":
        return f"      {{ data: {{ questionUuid: '{uuid}', questionType: 'MATRIX_SCALE', matrixScaleAnswers: state.answers['{uuid}'] || [] }} }}"
    if qtype == "UPLOAD":
        return f"      {{ data: {{ questionUuid: '{uuid}', questionType: 'UPLOAD', files: state.answers['{uuid}'] || [] }} }}"
    if qtype == "GENERIC":
        # 后端读取 GENERIC 答案的字段是 answerData（JSON 字符串）+ genericId，与 bridge buildSubmitData 一致；
        # 之前误用 value 字段 → 提交体里答案进不了后端 → 自定义题数据全空。
        return f"      {{ data: {{ questionUuid: '{uuid}', questionType: 'GENERIC', genericId: null, answerData: JSON.stringify(state.answers['{uuid}'] || {{}}) }} }}"
    return f"      {{ data: {{ questionUuid: '{uuid}', questionType: '{qtype}', value: state.answers['{uuid}'] }} }}"


def _build_js_event_handler(q: Dict[str, Any]) -> str:
    """为每道题生成基础事件处理逻辑。"""
    code = q["code"]
    uuid = q.get("uuid", code)
    qtype = _normalize_type(q.get("type", ""))

    if qtype == "RADIO":
        return f'''    // {code} —— 单选
    document.querySelectorAll('[data-question][data-code="{code}"] [data-option]').forEach(el => {{
      el.addEventListener('click', () => {{
        document.querySelectorAll('[data-question][data-code="{code}"] [data-option]').forEach(o => o.classList.remove('selected'));
        el.classList.add('selected');
        state.answers['{uuid}'] = [{{ label: el.textContent.trim(), value: el.dataset.optionValue, selected: true }}];
      }});
    }});'''

    if qtype == "CHECKBOX":
        # 多选用原生 checkbox：选中态归浏览器（:checked）。handler 只【读】当前勾选并同步 .selected 类，
        # 不做 toggle —— 纯读→渲染，幂等。即便被多处绑定也不会相互抵消（旧版两个 toggle 互消会导致"点了选不动"）。
        return f'''    // {code} —— 多选
    document.querySelectorAll('[data-question][data-code="{code}"] [data-option]').forEach(el => {{
      el.addEventListener('change', () => {{
        const opts = Array.from(document.querySelectorAll('[data-question][data-code="{code}"] [data-option]'));
        opts.forEach(o => {{
          const cb = o.querySelector('input[type="checkbox"]');
          o.classList.toggle('selected', !!(cb && cb.checked));
        }});
        state.answers['{uuid}'] = opts.filter(o => {{
          const cb = o.querySelector('input[type="checkbox"]'); return cb && cb.checked;
        }}).map(o => ({{
          label: (o.querySelector('[data-option-text]') || o).textContent.trim(), value: o.dataset.optionValue, selected: true
        }}));
      }});
    }});'''

    if qtype == "TEXTAREA":
        return f'''    // {code} —— 文本
    const ta_{code} = document.querySelector('[data-question][data-code="{code}"] textarea');
    if (ta_{code}) ta_{code}.addEventListener('input', e => {{ state.answers['{uuid}'] = e.target.value; }});'''

    if qtype == "SCALE":
        return f'''    // {code} —— 评分
    document.querySelectorAll('[data-question][data-code="{code}"] [data-scale-value]').forEach(el => {{
      el.addEventListener('click', () => {{
        document.querySelectorAll('[data-question][data-code="{code}"] [data-scale-value]').forEach(s => s.classList.remove('active'));
        el.classList.add('active');
        state.answers['{uuid}'] = parseInt(el.dataset.scaleValue);
      }});
    }});'''

    if qtype == "MATRIX_SCALE":
        return f'''    // {code} —— 矩阵评分
    document.querySelectorAll('[data-question][data-code="{code}"] [data-survey-role="matrix-row"]').forEach(row => {{
      const rowLabel = row.dataset.matrixRowLabel;
      row.querySelectorAll('[data-scale-value]').forEach(el => {{
        el.addEventListener('click', () => {{
          row.querySelectorAll('[data-scale-value]').forEach(s => s.classList.remove('active'));
          el.classList.add('active');
          if (!state.answers['{uuid}']) state.answers['{uuid}'] = [];
          const existing = state.answers['{uuid}'].find(a => a.rowTitle === rowLabel);
          if (existing) existing.score = parseInt(el.dataset.scaleValue);
          else state.answers['{uuid}'].push({{ rowTitle: rowLabel, score: parseInt(el.dataset.scaleValue) }});
        }});
      }});
    }});'''

    if qtype == "UPLOAD":
        return f'''    // {code} —— 上传
    const up_{code} = document.querySelector('[data-question][data-code="{code}"] input[type="file"]');
    if (up_{code}) {{
      up_{code}.addEventListener('change', e => {{
        const files = Array.from(e.target.files).map(f => ({{ url: URL.createObjectURL(f), fileName: f.name }}));
        state.answers['{uuid}'] = files;
      }});
    }}'''

    return f"    // {code} ({qtype}) —— 请自行添加交互逻辑"


# 短 checklist：引导 Agent 自写分页/提交，勿留半成品；禁止对全卷 [data-option] 绑自动翻页。
_PAGINATION_CHECKLIST = """
/*
 * Pagination checklist (implement it yourself; no half-finished work):
 * - [ ] If a "Next" DOM exists → must bind click → your next-page function
 * - [ ] Only type=8 (RADIO) may auto-advance via setTimeout after selection
 * - [ ] Types 9/10/28/39 must not auto-page on option/scale clicks
 * - [ ] Submit: visible control → submitSurvey() or submitAndStay (see submit-stay-pattern)
 * - [ ] Don't use submit-validation-failure page jumps as a fake "Next"
 * - [ ] Navigation: fixed bottom bar or inside the question card; don't let an absolute question card cover pre-question navigation
 * - [ ] "Visible" = can be seen and clicked, not merely present in the DOM
 * - [ ] With 'use strict', variables inside IIFEs must be explicitly declared (var/let/const); undeclared assignment is forbidden (else ReferenceError → only the nav bar shows, questions all white)
 * Same-device answer draft: enabled by default in the skeleton (restores answers only, not the page). Hand-writing answers localStorage again is forbidden.
 * 可选停页：翻页时 notifyFreeDraftPage(n)；window.onFreeDraftPageRestore = (p) => showPage(p)
 * 关闭答案草稿：window.SURVEY_FREE_ANSWER_DRAFT_DEFAULT = false（须在本草稿脚本执行前）
 */
"""

_CSS_REGION_BEGIN = "/* ===== LLM 自定义 CSS 区域 BEGIN ===== */"
_CSS_REGION_END = "/* ===== LLM 自定义 CSS 区域 END ===== */"
_JS_REGION_BEGIN = "/* ===== LLM 自定义交互逻辑区域 BEGIN ===== */"
_JS_REGION_END = "/* ===== LLM 自定义交互逻辑区域 END ===== */"
_EVENT_HANDLER_FENCE = "/* ===== 以下为基础事件处理"


def _build_initial_css() -> str:
    """生成 survey-ui.css 初始内容：仅一个空的自定义样式区。
    free 默认不带任何样式（样式由问卷自行定义）；评测的默认样式 base-free.css 由 generate_assessment.py 在确认评测后注入。"""
    return f"""{_CSS_REGION_BEGIN}

{_CSS_REGION_END}
"""


def _ensure_survey_ui_css(output_dir: Path, *, force: bool = False) -> None:
    """确保输出目录有自由模式 survey-ui.css。

    - 已存在且非 force：不覆盖（保留 LLM 已写样式）。
    - 缺失：写入空的 LLM 自定义 CSS 骨架（与标准模式不同，不从 questionareTemplates 拷基座）。
    - force=True：按骨架脚本约定覆盖为空骨架（调用方须先备份）。
    """
    css_path = output_dir / "survey-ui.css"
    existed = css_path.is_file()
    if existed and not force:
        return
    css_path.write_text(_build_initial_css(), encoding="utf-8")
    if force and existed:
        print(f"已覆盖写入自由模式 CSS 骨架: {css_path}")
    else:
        print(f"已补写自由模式 CSS 骨架: {css_path}")


# 白屏守卫：自由模式显隐由问卷脚本掌控，门切换忘了恢复可见区会整屏白屏；守卫在白屏时保守自愈。
_RENDER_GUARD_MARKER = "RENDER_GUARD"
_RENDER_GUARD_SCRIPT = _read_asset("render-guard.html")


_FREE_ANSWER_VALIDATION_JS = _asset_inner_js("free-answer-validation.html")
_FREE_ANSWER_DRAFT_JS = _asset_inner_js("free-answer-draft.html")


def _build_survey_ui_js(event_handlers: str, answer_entries: str, locale: str = DEFAULT_LOCALE) -> str:
    """生成 survey-ui.js 初始内容（body 尾 script 迁出）。
    EVAL_SHARE 评测分享套件不再无条件嵌入；仅评测卷由 generate_assessment.py 注入。"""
    validation_block = _FREE_ANSWER_VALIDATION_JS.strip()
    draft_block = _FREE_ANSWER_DRAFT_JS.strip()
    return f"""{free_mode_i18n_prelude(locale)}
{_JS_REGION_BEGIN}
{_PAGINATION_CHECKLIST}
{_JS_REGION_END}

{_EVENT_HANDLER_FENCE} ===== */

{event_handlers}

{validation_block}

function buildAnswers() {{
  return [
{answer_entries}
  ];
}}

function submitSurvey() {{
  if (window.WJFreeValidation) {{
    const v = window.WJFreeValidation.validateAll({{ toast: true }});
    if (!v.ok) return;
  }}
  if (typeof window.clearFreeAnswerDraft === 'function') window.clearFreeAnswerDraft();
  const answers = buildAnswers();
  window.SurveyDataBridge.submit(answers, document.documentElement.outerHTML);
}}

{draft_block}
"""


def generate_skeleton(schema: Dict[str, Any], page_by_code: Dict[str, int] | None = None, locale: str = DEFAULT_LOCALE) -> str:
    """根据 schema 生成完整 HTML 骨架。"""
    questions = _extract_questions(schema)
    survey_title = schema.get("survey", {}).get("title", "问卷")
    lang = resolve_locale(locale)

    # Build independent page-break nodes as direct children of the survey root.
    page_copy = html_dict_for_locale(locale)["pageBreak"]
    question_blocks: list[str] = []
    current_page: int | None = None
    for i, q in enumerate(questions):
        page = int((page_by_code or {}).get(str(q.get("code", "")), 1))
        if page != current_page:
            label = page_copy.format(n=page)
            question_blocks.append(
                f'    <div class="pb" data-page-break="{page}"><span>{html_escape(label, quote=False)}</span></div>'
            )
            current_page = page
        question_blocks.append(_build_question_html(q, i + 1, page_by_code, locale=locale))
    question_doms = "\n\n".join(question_blocks)

    return f'''<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="UTF-8">
  <title>{html_escape(survey_title, quote=False)}</title>
  <link rel="stylesheet" href="./survey-ui.css" data-inject="survey-css">
  <script src="./survey-ui.js" data-inject="survey-js" defer></script>
  <script src="{SURVEY_BRIDGE_URL}"></script>
  <script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js"></script>
  <script>
    // 答案状态 + 全局 submitGenericAnswer 包装：必须放在 <head>（题目内联脚本之前）安装。
    // 题目脚本在解析期就可能调用 submitGenericAnswer（如排序题初始化即提交默认顺序），
    // 若包装晚于题目脚本，这些早期提交会被原始 bridge 函数吞掉、进不了 state.answers。
    var state = {{ answers: {{}} }};
    (function () {{
      var _origSGA = window.submitGenericAnswer;
      window.submitGenericAnswer = function (uuid, answers) {{
        if (uuid && answers && typeof answers === 'object' && Object.keys(answers).length) {{
          state.answers[uuid] = answers;
        }}
        if (typeof _origSGA === 'function') {{ try {{ _origSGA(uuid, answers); }} catch (e) {{}} }}
      }};
    }})();
  </script>
{_RENDER_GUARD_SCRIPT}
</head>
<body class="free" data-survey-mode="free">
  <div data-survey-role="survey" data-survey-mode="free">
{question_doms}

    <!-- QUESTION_INSERT_POINT: 题目列表区域结束（用于定位题目插入位置，不受条件判断影响） -->
    <!-- SUBMIT_ENTRY: Agent 提供可点提交，调用 submitSurvey / submitAndStay -->
  </div>
</body>
</html>'''


def build_survey_ui_js_for_schema(schema: Dict[str, Any], locale: str = DEFAULT_LOCALE) -> str:
    """根据 schema 生成 survey-ui.js 内容（供 main 与测试复用）。"""
    questions = _extract_questions(schema)
    answer_entries = ",\n".join(_build_js_answer_entry(q) for q in questions)
    event_handlers = "\n\n".join(_build_js_event_handler(q) for q in questions)
    return _build_survey_ui_js(event_handlers, answer_entries, locale=locale)


def main() -> int:
    parser = argparse.ArgumentParser(description="自由模式骨架生成器")
    parser.add_argument("--spec", required=True, help="survey_spec.json 路径（统一 questions 数组格式）")
    parser.add_argument("--output-dir", default=None, help="输出目录；默认写到 --spec 所在目录")
    parser.add_argument("--output", default="survey-unified-generate.html", help="输出 HTML 文件名（相对于 --output-dir 或 --spec 所在目录）")
    parser.add_argument("--force", action="store_true", help="强制覆盖已存在的 HTML 文件")
    parser.add_argument("--locale", default=DEFAULT_LOCALE, help="回答端 UI 文案语种（如 zh-CN / en-US / es-MX）")
    parser.add_argument(
        "--i18n-dict",
        default=None,
        help="额外语种字典 JSON（{locale: {key: value}}），用于主字典未覆盖的语种（如韩语 ko）；key 清单与示例见 references/i18n-dict.example.json",
    )
    args = parser.parse_args()

    spec_path = Path(args.spec)
    if args.i18n_dict:
        load_locale_dict_file(args.i18n_dict)
    warn_if_custom_locale_needed(args.locale, args.i18n_dict)
    if not spec_path.exists():
        print(f"❌ Spec 文件不存在: {spec_path}")
        return 1

    # 默认输出目录与标准模式一致：写到 --spec 所在目录
    output_dir = Path(args.output_dir) if args.output_dir else spec_path.parent
    output_path = output_dir / args.output
    if output_path.exists() and not args.force:
        print(f"⚠️ 骨架文件已存在: {output_path}")
        print(f"   如需重新生成（会覆盖已有编辑），请加 --force 参数。")
        print(f"   如需继续编辑现有文件，请直接读取并修改，不要重新跑本脚本。")
        return 0

    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ spec JSON 解析失败：{e}")
        print("   Build the spec with an available deterministic JSON writer and retry.")
        return 1

    # 从原始 spec 构建 code→page 映射（schema 中不含 page 字段）
    try:
        page_by_code: Dict[str, int] = {
            q["code"]: int(q.get("page", 1)) for q in spec.get("questions", [])
        }
    except (KeyError, TypeError):
        print("❌ A question is missing code. Every question needs title/type/code; choice questions also need options.")
        return 1

    # 兜底常见可选字段，避免因缺 description 等非关键字段在 build_schema 里 KeyError（评测/简单卷常漏）
    spec.setdefault("survey", {})
    if isinstance(spec.get("survey"), dict):
        spec["survey"].setdefault("description", "")
    for _q in spec.get("questions", []):
        if isinstance(_q, dict):
            _q.setdefault("description", "")

    # 复用标准模式的 spec → schema 转换逻辑
    import sys
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    import generate_standard_survey as std_module

    try:
        std_module.validate_spec_structure(spec, require_survey=True)
        std_module.validate_spec_chart_html(spec)
    except ValueError as e:
        print(f"❌ spec 结构或 chartHtml 校验失败：{e}")
        print("   Check title/type/code and ensure every GENERIC chartHtml is valid, then retry.")
        return 1

    try:
        tmpl = std_module.load_system_json_template()
        questions = std_module.parse_questions(spec, locale=args.locale)
        schema = std_module.build_schema(spec, tmpl, questions, locale=args.locale)
    except Exception as e:
        bad = ""
        for i, q in enumerate(spec.get("questions", []), 1):
            if not isinstance(q, dict) or not q.get("title") or not q.get("type") or not q.get("code"):
                bad = f"（疑似第 {i} 题有问题：{(q.get('code') or q.get('title')) if isinstance(q, dict) else q}）"
                break
        print(f"❌ spec→schema 转换失败：{e} {bad}")
        print("   Check title/type/code and non-empty choice options, then retry.")
        return 1

    # 写出 question_schema_generate.json（与 HTML 同目录）
    schema_path = output_path.parent / "question_schema_generate.json"
    schema_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✅ 已生成: {schema_path}")

    html = generate_skeleton(schema, page_by_code=page_by_code, locale=args.locale)
    output_path.write_text(html, encoding="utf-8")
    print(f"✅ 骨架已生成: {output_path}")

    # 自由模式：样式写入 survey-ui.css；交互写入 survey-ui.js（HTML head 外链引用）
    # 本路径为首次生成或 --force：须写成自由模式空骨架（覆盖 bootstrap 拷入的标准 CSS）
    css_path = output_path.parent / "survey-ui.css"
    js_path = output_path.parent / "survey-ui.js"
    _ensure_survey_ui_css(output_path.parent, force=True)
    js_path.write_text(build_survey_ui_js_for_schema(schema, locale=args.locale), encoding="utf-8")
    print(f"✅ 已生成: {css_path}")
    print(f"✅ 已生成: {js_path}")

    all_questions = _extract_questions(schema)
    print(f"   共 {len(all_questions)} 道题: {', '.join(q['code'] for q in all_questions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
