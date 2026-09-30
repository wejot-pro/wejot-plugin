#!/usr/bin/env python3
"""评测骨架生成器（第二段，跑在 generate_free_mode_skeleton.py 之后）。

输入：已生成的自由模式骨架 survey-unified-generate.html + 一份评测配置 eval_config.json（纯数据）。
作用：在骨架上**自动注入**评测的「开场页 + 结果页 + 逐题翻页 + 计分/结果渲染」，
     并把"最后一题→提交"改成"最后一题→显示结果页"，隐藏基座提交按钮。
     评测 CSS/JS 写入 survey-ui.css / survey-ui.js；HTML 仅注入 DOM 浮层。
     落库与分享(复制/海报)由 survey-ui.js 内置的 EVAL_SHARE 套件自动接管，无需本脚本处理。
LLM 只需提供 eval_config（题目计分映射 + 结果类型文案 + 开场文案），不用手写任何结果页 HTML/JS/CSS。

用法：
    python generate_assessment.py --html survey-unified-generate.html --config eval_config.json

eval_config.json 结构见 references/eval_config.example.json。
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
    ensure_default_submit_button,
    inject_js_to_survey_ui,
    parse_questions,
    resolve_header,
    scoring_by_uuid,
    submit_button_for_locale,
)
from survey_ui_i18n import (
    html_dict_for_locale,
    load_locale_dict_file,
    warn_if_custom_locale_needed,
)

_EVAL_SHARE_JS = asset_inner_js("eval-share.html")

_ASSESSMENT_CSS_MARKER = "/* ===== 评测脚手架 CSS（generate_assessment.py） ===== */"
_INJECT_MARKER = "generate_assessment.py 注入"


def _check_config(config: dict, code2uuid: dict, q_codes: list) -> list:
    """配置自检：不报错只提醒，帮 LLM 发现"漏计分/类型没定义"这类静默坑。"""
    warns = []
    model = config.get("model", "dimension")
    scoring = config.get("scoring") or {}
    missing = [c for c in q_codes if c not in scoring]
    if missing:
        warns.append(f"These questions have no scoring mapping in scoring and will not be scored: {', '.join(missing)}")
    unknown_q = [c for c in scoring if c not in code2uuid]
    if unknown_q:
        warns.append(f"These codes in scoring do not exist among the questions (typo?): {', '.join(unknown_q)}")
    if model == "dimension":
        types = config.get("types") or {}
        if not types:
            warns.append("model=dimension but no types config (result-type copy) was provided")
        used = set()
        for code, m in scoring.items():
            for opt, key in (m or {}).items():
                used.add(key)
                if key not in types:
                    warns.append(f"scoring[{code}][{opt}] 指向的类型 '{key}' 在 types 里没定义")
        for k in types:
            if k not in used:
                warns.append(f"类型 '{k}' 定义了但没有任何选项指向它（永远出不来）")
        chips = (config.get("intro") or {}).get("chips") or []
        if types and len(chips) < len(types):
            warns.append(
                f"intro.chips 只列了 {len(chips)} 个，少于 types 的 {len(types)} 个角色——已自动用 types 补全开场页（要自定义请在 intro.chips 列全）"
            )
        n_scored = len([c for c in scoring if c in code2uuid])
        if types and n_scored < len(types):
            warns.append(
                f"只有 {n_scored} 道计分题却有 {len(types)} 个类型，多数类型很难成为结果（建议计分题数 ≥ 类型数，每个类型有足够选项指向）"
            )
    else:
        if not (config.get("bands")):
            warns.append("model=sum 但没有 bands（分档）")
        for code, m in scoring.items():
            for opt, sc in (m or {}).items():
                if not isinstance(sc, (int, float)):
                    warns.append(f"scoring[{code}][{opt}] 在 sum 模型下应是数字分值，当前是 {sc!r}")
    return warns


def _build_overlays(config: dict, header: str = "", *, locale: str | None = None) -> str:
    ui = html_dict_for_locale(locale)
    intro = config.get("intro") or {}
    chip_items = list(intro.get("chips") or [])
    if config.get("model", "dimension") == "dimension":
        types = config.get("types") or {}
        derived = [f'{str(t.get("emoji") or "").strip()} {t.get("title") or k}'.strip() for k, t in types.items()]
        if len(chip_items) < len(derived):
            chip_items = derived
    chips = "".join(f'<span class="eval-chip">{h(str(c))}</span>' for c in chip_items)
    title = h(str(intro.get("title") or ui["startTest"]))
    sub = h(str(intro.get("sub") or ""))
    header_img = f'<img class="eval-intro-img" src="{h(header, quote=True)}" alt="" />' if header else ""
    return f"""
  <!-- ===== 评测脚手架·开场页/结果页/翻页钮（generate_assessment.py 注入；样式见 survey-ui.css） ===== -->

  <!-- 开场诱饵页 -->
  <div id="eval-intro" class="eval-layer" style="display:none">
    <div class="eval-card">
      {header_img}
      <h1 class="eval-intro-title">{title}</h1>
      <p class="eval-intro-sub">{sub}</p>
      <div class="eval-sample">{chips}</div>
      <button id="eval-start" class="eval-btn-primary">{ui["startTest"]} →</button>
    </div>
  </div>

  <!-- 逐题翻页：底部「下一题 / 查看结果」 -->
  <div id="eval-next"><button type="button">{ui["nextQuestion"]}</button></div>

  <!-- 结果页（落库 + 复制/海报由 EVAL_SHARE 套件自动接管，标准 id 不要改） -->
  <div id="eval-result" class="eval-layer" style="display:none">
    <div class="eval-card">
      <div id="eval-result-emoji" class="eval-result-emoji"></div>
      <h1 id="eval-result-title" class="eval-result-title"></h1>
      <div id="eval-result-score" class="eval-result-score"></div>
      <p id="eval-result-desc" class="eval-result-desc"></p>
      <div id="eval-result-sections"></div>
    </div>
    <div class="eval-share eval-actionbar">
      <button id="eval-poster" class="eval-btn-primary">{ui["poster"]}</button>
      <button id="eval-copy" class="eval-btn-ghost">{ui["share"]}</button>
      <button id="eval-retry" class="eval-btn-ghost">{ui["retry"]}</button>
    </div>
  </div>
"""


def _build_assessment_css() -> str:
    return f"""{_ASSESSMENT_CSS_MARKER}
/* 逐题模式：卷面容器撑满视口高度，当前题卡片垂直居中（与开场页一致）；题目长于一屏则自然撑高可滚动，不裁切 */
[data-survey-role="survey"] {{ min-height: 100vh; display: flex; flex-direction: column; justify-content: center; padding-bottom: 96px; }}
[data-survey-role="survey"] [data-question] {{ display: none; }}
[data-survey-role="survey"] [data-question].active {{ display: block; width: 100%; min-width: 0; }}
#eval-next {{ position: fixed; left: 0; right: 0; bottom: 0; z-index: 50; display: none; justify-content: center;
  padding: 12px 16px calc(12px + env(safe-area-inset-bottom)); background: #fff; box-shadow: 0 -4px 16px rgba(0,0,0,.06); }}
#eval-next > button {{ width: 100%; max-width: 360px; padding: 15px; border: 0; border-radius: 12px;
  background: #5b8cff; color: #fff; font-size: 16px; font-weight: 600; cursor: pointer; }}
.eval-progress {{ height: 6px; background: #eceef1; border-radius: 999px; overflow: hidden; margin: 4px 0 18px; }}
.eval-progress > i {{ display: block; height: 100%; width: 0; background: #5b8cff; transition: width .25s; }}
.eval-sec {{ text-align: left; background: #f5f7fb; border: 1px solid #e7eaf2; border-radius: 12px; padding: 14px 16px; margin: 12px 0; }}
.eval-sec-t {{ font-weight: 700; margin-bottom: 6px; color: #2b59d6; }}
.eval-sec-b {{ color: #4a5159; line-height: 1.7; font-size: 15px; }}
.eval-intro-img {{ width: 100%; max-width: 320px; border-radius: 16px; margin: 0 auto 18px; display: block; box-shadow: 0 6px 20px rgba(0,0,0,.1); }}
"""


def _append_assessment_css(work_dir: Path) -> None:
    css_path = work_dir / "survey-ui.css"
    prefix = base_free_css_prefix(css_path.read_text(encoding="utf-8") if css_path.is_file() else "")
    append_css_marker(work_dir, _ASSESSMENT_CSS_MARKER, _build_assessment_css(), prefix=prefix)


def _build_js(config: dict, code2uuid: dict) -> str:
    cfg = {
        "model": config.get("model", "dimension"),
        "types": config.get("types") or {},
        "_typeOrder": list((config.get("types") or {}).keys()),
        "bands": config.get("bands") or [],
        "sectionOrder": config.get("sectionOrder") or [],
        "scoring": scoring_by_uuid(config.get("scoring") or {}, code2uuid),
    }
    cfg_json = json.dumps(cfg, ensure_ascii=False)
    return """
    /* ===== 评测脚手架·逻辑（generate_assessment.py 注入）：开场→逐题→结果。落库/分享由套件自动接管 =====
       想自定义计分/结果渲染，可改本块；想换 UI 改上方注入的 HTML 或 survey-ui.css。这是默认实现、不是限制。 */
    (function () {
      var EVAL = __EVAL_CONFIG__;
      function byId(id) { return document.getElementById(id); }
      function setText(id, v) { var e = byId(id); if (e) e.textContent = v == null ? '' : v; }
      var questions = Array.prototype.slice.call(document.querySelectorAll('[data-survey-role="survey"] [data-question]'));
      var cur = 0;

      function selVal(q) { var a = state.answers[q.dataset.questionUuid]; return (a && a[0]) ? a[0].value : null; }
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

      function syncNextBtn() {
        var nb = byId('eval-next'); if (!nb) return;
        var last = cur >= questions.length - 1;
        var btn = nb.querySelector('button'); if (btn) btn.textContent = last ? _suiT('viewMyResult') : _suiT('nextQuestion');
        nb.style.display = (last && !answered(questions[cur])) ? 'none' : 'flex';
      }
      function showQ(idx) {
        questions.forEach(function (q, i) { q.classList.toggle('active', i === idx); });
        cur = idx; window.scrollTo(0, 0);
        var pf = byId('eval-progress-fill'); if (pf) pf.style.width = ((idx + 1) / questions.length * 100) + '%';
        syncNextBtn();
      }
      function next() {
        if (window.WJFreeValidation) {
          var v = WJFreeValidation.validateQuestion(questions[cur], { toast: true });
          if (!v.ok) return;
        } else if (!answered(questions[cur])) { alert(_suiT('chooseOne')); return; }
        if (cur < questions.length - 1) showQ(cur + 1); else finish();
      }
      function start() { var i = byId('eval-intro'); if (i) i.style.display = 'none'; showQ(0); }

      function compute() {
        if (EVAL.model === 'sum') {
          var total = 0;
          Object.keys(EVAL.scoring).forEach(function (u) {
            var q = byUuid(u); if (!q) return; var v = selVal(q), m = EVAL.scoring[u];
            if (v != null && m[v] != null) total += Number(m[v]) || 0;
          });
          var band = null, bands = EVAL.bands || [];
          for (var i = 0; i < bands.length; i++) { if (total <= (bands[i].max != null ? bands[i].max : 1e9)) { band = bands[i]; break; } }
          if (!band) band = bands[bands.length - 1] || {};
          var r = {}; for (var k in band) r[k] = band[k]; r._total = total; return r;
        }
        var tally = {};
        Object.keys(EVAL.scoring).forEach(function (u) {
          var q = byUuid(u); if (!q) return; var v = selVal(q); var key = v != null ? EVAL.scoring[u][v] : null;
          if (key) tally[key] = (tally[key] || 0) + 1;
        });
        var order = (EVAL._typeOrder && EVAL._typeOrder.length) ? EVAL._typeOrder : Object.keys(EVAL.types);
        var best = order[0];
        order.forEach(function (k) { if ((tally[k] || 0) > (tally[best] || 0)) best = k; });
        var t = EVAL.types[best] || {}; var r = { _key: best }; for (var k in t) r[k] = t[k]; return r;
      }
      function byUuid(u) { for (var i = 0; i < questions.length; i++) if (questions[i].dataset.questionUuid === u) return questions[i]; return null; }

      function render(r) {
        setText('eval-result-emoji', r.emoji || '🎯');
        setText('eval-result-title', r.title || _suiT('myResult'));
        setText('eval-result-score', r.label || (r._total != null ? (_suiT('totalScore') + ' ' + r._total) : ''));
        setText('eval-result-desc', r.desc || '');
        var box = byId('eval-result-sections'); if (box) {
          box.innerHTML = '';
          (EVAL.sectionOrder || []).forEach(function (name) {
            var txt = (r.sections || {})[name]; if (!txt) return;
            var d = document.createElement('div'); d.className = 'eval-sec';
            var t = document.createElement('div'); t.className = 'eval-sec-t'; t.textContent = name;
            var b = document.createElement('div'); b.className = 'eval-sec-b'; b.textContent = txt;
            d.appendChild(t); d.appendChild(b); box.appendChild(d);
          });
        }
      }
      function formatEvalDisplay(r) {
        if (r._total != null) return String(r._total);
        return (r.title || '').trim();
      }
      function finish() {
        var r = compute();
        window.__WJ_EVAL_RESULT__ = formatEvalDisplay(r);
        render(r);
        var nb = byId('eval-next'); if (nb) nb.style.display = 'none';
        var res = byId('eval-result'); if (res) res.style.display = 'flex';
      }

      questions.forEach(function (q, idx) {
        if (q.getAttribute('data-question-type') !== '8') return;
        q.querySelectorAll('[data-option]').forEach(function (opt) {
          opt.addEventListener('click', function () { setTimeout(function () { if (cur === idx) next(); }, 280); });
        });
      });

      var _surveyRoot = document.querySelector('[data-survey-role="survey"]');
      if (_surveyRoot) ['click', 'input', 'change'].forEach(function (ev) {
        _surveyRoot.addEventListener(ev, function () { setTimeout(syncNextBtn, 0); });
      });

      function wire() {
        var s = byId('eval-start'); if (s) s.addEventListener('click', start);
        var n = byId('eval-next'); if (n) n.querySelector('button').addEventListener('click', next);
        var rt = byId('eval-retry'); if (rt) rt.addEventListener('click', function () { location.reload(); });
        var i = byId('eval-intro'); if (i) i.style.display = 'flex';
      }
      if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire); else wire();
    })();
""".replace("__EVAL_CONFIG__", cfg_json)


def apply_assessment(html: str, config: dict, html_dir: Path, *, locale: str | None = None):
    qs = parse_questions(html)
    if not qs:
        raise ValueError("No [data-question] found in the skeleton; confirm generate_free_mode_skeleton.py ran first")
    code2uuid = {c: u for c, u, _ in qs}
    q_codes = [c for c, _, _ in qs]

    header = resolve_header(config, html_dir)
    warns = _check_config(config, code2uuid, q_codes)
    overlays = _build_overlays(config, header, locale=locale)
    js = _build_js(config, code2uuid)

    # free 骨架默认不再带提交钮；评测脚手架依赖该锚点隐藏并挂 overlays
    html = ensure_default_submit_button(html, hidden=True, locale=locale)

    submit_btn = submit_button_for_locale(locale)
    hidden_btn = submit_button_for_locale(locale, hidden=True)
    if submit_btn in html:
        html = html.replace(
            submit_btn + "\n  </div>",
            hidden_btn + "\n  </div>\n" + overlays,
            1,
        )
    elif hidden_btn + "\n  </div>" in html:
        html = html.replace(
            hidden_btn + "\n  </div>",
            hidden_btn + "\n  </div>\n" + overlays,
            1,
        )
    elif overlays.strip() not in html:
        html = html.replace('  </div>\n</body>', '  </div>\n' + overlays + '\n</body>', 1)

    html = inject_js_to_survey_ui(html_dir, js, html, marker=_INJECT_MARKER)
    _append_assessment_css(html_dir)
    append_js_asset(html_dir, _EVAL_SHARE_JS, fence_marker="EVAL_SHARE BEGIN")

    return html, warns, header


def main() -> int:
    ap = argparse.ArgumentParser(description="Assessment skeleton generator (runs after the free skeleton)")
    ap.add_argument("--html", required=True, help="survey-unified-generate.html generated by generate_free_mode_skeleton.py")
    ap.add_argument("--config", required=True, help="评测配置 eval_config.json")
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
    if not html_path.is_file():
        print(f"❌ HTML does not exist: {html_path}")
        return 1
    if not cfg_path.is_file():
        print(f"❌ config does not exist: {cfg_path}")
        return 1
    try:
        config = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ Failed to parse eval_config.json; create it with an available deterministic JSON writer: {e}")
        return 1

    try:
        out, warns, header = apply_assessment(
            html_path.read_text(encoding="utf-8"), config, html_path.parent, locale=args.locale
        )
    except Exception as e:
        print(f"❌ Injection failed: {e}")
        return 1

    html_path.write_text(out, encoding="utf-8")
    nq = len(parse_questions(out))
    print(f"✅ Assessment scaffolding injected (opening/per-question/result-page DOM + scoring JS/CSS), {nq} question(s). Persistence/sharing handled by the EVAL_SHARE suite automatically.")
    if header:
        print(f"   开场页已用头图：{header}")
    if warns:
        print(f"⚠️ 配置自检发现 {len(warns)} 处可能的问题（不阻断，建议核对 eval_config）：")
        for w in warns:
            print("   - " + w)
    print("   下一步：在浏览器/无头渲染确认开场→答题→结果三屏跑通；要调结果文案改 eval_config 重跑即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
