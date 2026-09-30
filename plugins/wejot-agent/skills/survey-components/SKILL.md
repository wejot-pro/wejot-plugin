---
name: survey-components
description: Design or revise a specialized WeJot GENERIC question when standard radio, checkbox, text, upload, scale, or matrix-scale types cannot express the requested interaction or answer contract.

---

# Survey Components

## What this skill does

- Provide unified interaction, styling, responsive, and accessibility constraints for custom question types.
- Provide strict constraint checklists per question type to avoid generating non-compliant components.
- Provide a reference-document index per question type for on-demand deep reads.

## Mandatory prerequisite references (must follow)

- Follow `survey-create` for the surrounding questionnaire artifact workflow.
- Before writing `GENERIC` question code (`answerKeys/genericStyle/genericHtml/genericScript/chartHtml`), you must first consult:
  - [references/minimal_survey_spec.json](references/minimal_survey_spec.json) for the structure contract.
  - [references/minimal_survey_spec.example.json](references/minimal_survey_spec.example.json) for shape only; copying its business topic, question copy, or UUIDs is forbidden.
  - Align carefully with the GENERIC example snippet in that file (about lines 66–83).
- It is forbidden to improvise based on general frontend experience alone; if the generated result is incompatible with the example structure above, correct it against that example.
- The final script must comply with template conventions: read values via `wrapper`/`.gc`, provide `getCurrentAnswer()`, and call `submitAnswer(...)` on `survey:before-submit` and on user interaction changes.

## Whole-survey acceptance for GENERIC work

Whenever a task adds, changes, appends, rebuilds, or relocates a GENERIC question—or changes its answer keys, HTML, CSS, JavaScript, sample answer, or statistics chart—maintain a durable TODO describing the requirement source, affected artifacts, expected answer contract, integration points, and acceptance criteria. Reuse an existing questionnaire TODO when one already covers the same work.

After implementation, delegate an independent reviewer when the host supports it. The reviewer must test the complete respondent journey rather than only the custom fragment: standard and GENERIC answers, navigation, required and format validation, answer persistence, submission, coexistence with other questions, and any reporting contract. Give the reviewer the original requirements, current four-artifact bundle, this skill, the matching component rule, and the bundled references needed to evaluate the result.

Record findings in the TODO, fix failures, and repeat independent review. When no independent reviewer is available, perform the same whole-survey acceptance explicitly and record the limitation. Do not treat fragment-only inspection or structural validation as delivery acceptance.

## genericScript writing spec (mandatory for all custom question types)

- **genericScript is a bare code fragment**; at runtime it is inserted into the outer template's `try{}` block and executed.
- The outer template already provides the following variables/functions, usable directly:
  - `wrapper`: points to the `.gx` element
  - `questionId`: current question UUID
  - `submitAnswer(obj)`: submit the answer
  - `getCurrentAnswer()`: get the current answer (can be overridden inside genericScript)
- **genericScript only handles the current GENERIC question's own interaction and answer submission** (e.g. button clicks, form input, custom component initialization).
- **Forbidden** in genericScript: implementing questionnaire-level logic — show/hide control, branch jumps, option references, cross-question answer reads, etc. Such logic must be centralized in the `survey-ui.js` business-logic extension area, via `registerUserLogic` / `onLogicAnswerChange` / `setLogicQuestionVisibility` / `setQuestionItems`.
- **Forbidden** in genericScript: listening to the `surveyAnswerChanged` event.
- **Forbidden** in genericScript: wrapping in an IIFE `(function(){...})()`.
- **Forbidden**: using `document.currentScript` (it is already null at execution time).
- DOM lookup must go through the outer `wrapper`: `var c=wrapper&&wrapper.querySelector('.gc');`
- `answerKeys` must match `data-answer-keys`, and keys returned by `getCurrentAnswer()` must be in `answerKeys`. NPS is fixed to `answer`; for other self-built types (not SurveyComponents prebuilt components), prefer Chinese keys (dimension/field/option copy) consistent with `userAnswersSample`; key names must not contain English commas.

## If using a prebuilt script to add a custom question, follow this excerpt from [references/minimal_survey_spec.example.json](references/minimal_survey_spec.example.json)
```json
{
  "survey": {
    "title": "All question types example survey",
    "description": "Minimal configuration demonstrating standard and custom question types"
  },
  "questions": [
    {
      "title": "Please complete a custom interaction question",
      "type": "GENERIC",
      "required": false,
      "page": 2,
      "code": "custom_interaction_question",
      "description": "Custom question type (NPS three-level example). Actual GENERIC question specs must follow the survey-components skill.",
      "answerKeys": ["answer"],
      "userAnswersSample": [
        { "answer": 10 },
        { "answer": 9 },
        { "answer": 8 }
      ],
      "genericStyle": ".nps-wrap{display:flex;flex-direction:column;gap:12px;width:100%;max-width:719px;margin:0;padding:0;background:0 0;border-radius:0}.nps-label{font-size:14px;line-height:20px;color:var(--text-secondary,#6b7280)}.nps-scale{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.nps-btn{height:44px;border-radius:22px;border:1px solid var(--line-color,#e5e7eb);background:var(--bg-color,#fff);color:var(--text-primary,#111827);font-size:14px;line-height:1;cursor:pointer;transition:all .2s}.nps-btn:hover{border-color:var(--primary-color,#2563eb)}.nps-btn.is-active{background:var(--primary-color,#2563eb);border-color:var(--primary-color,#2563eb);color:#fff}.nps-tip{font-size:12px;line-height:18px;color:var(--text-tertiary,#9ca3af)}",
      "genericHtml": "<div class=\"nps-wrap\" role=\"group\" aria-label=\"NPS 0-10\">\\n  <div class=\"nps-label\">0=Not at all likely, 10=Extremely likely</div>\\n  <div class=\"nps-scale\" data-role=\"nps-scale\">\\n    <button type=\"button\" class=\"nps-btn\" data-nps=\"0\" aria-label=\"0\">0</button><button type=\"button\" class=\"nps-btn\" data-nps=\"5\" aria-label=\"5\">5</button><button type=\"button\" class=\"nps-btn\" data-nps=\"10\" aria-label=\"10\">10</button>\\n  </div>\\n  <div class=\"nps-tip\" data-role=\"nps-tip\" aria-live=\"polite\">Please select</div>\\n</div>",
      "genericScript": "var c=wrapper&&wrapper.querySelector('.gc');if(!c)return;var s=null,sc=c.querySelector('[data-role=\"nps-scale\"]'),tip=c.querySelector('[data-role=\"nps-tip\"]');function getCurrentAnswer(){return typeof s==='number'?{answer:s}:{}}function refreshUI(){var bs=c.querySelectorAll('.nps-btn[data-nps]');for(var i=0;i<bs.length;i++){var v=Number(bs[i].getAttribute('data-nps')),a=v===s;bs[i].classList.toggle('is-active',a);bs[i].setAttribute('aria-pressed',a?'true':'false')}if(tip)tip.textContent=typeof s==='number'?('Selected '+s):'Please select'}if(sc&&!sc._npsBound){sc._npsBound=true;sc.addEventListener('click',function(e){var b=e.target&&e.target.closest('.nps-btn[data-nps]');if(!b)return;s=Number(b.getAttribute('data-nps'));refreshUI();submitAnswer(getCurrentAnswer())})}if(wrapper&&!wrapper._surveyBeforeSubmitBound){wrapper._surveyBeforeSubmitBound=true;window.addEventListener('survey:before-submit',function(){var a=getCurrentAnswer();if(a&&Object.keys(a).length>0)submitAnswer(a)})}refreshUI();",
      "chartHtml": "<!--\n========== This string holds the custom statistics chart code. Only output the HTML from "Chart section start" to "Chart section end"; do not output the comment section below. ==========\nComment start\n - Purpose: this string is inserted into the survey statistics page (host page) to render the custom question type's statistics chart.\n - Forbidden: must NOT contain <!doctype>, <html>, <head>, <body>, or framework-region script (hasData/applyData, #chart-data-json parsing, etc.); no comments inside the code.\n - Must keep: the two divs #chart-no-data and #chart-content below, and the <script> defining window.renderChart(userAnswers, answerKeys).\n - renderChart: the framework calls it automatically when data exists. Parameters: userAnswers=array of user answer objects (each element is a key-value object; keys are the names in answerKeys, values are the answer values, possibly objects, matching your designed submission data), answerKeys=array of submission keys (matching your designed submission data keys); container show/hide and data parsing are handled by the framework.\n - **Encoding requirements (important!):** strictly follow the **Custom Question Type - Custom Statistics Chart Spec** section in the survey-components SKILL for rendering approach, decision logic, design constraints, and hard limits.\nComment end\n-->\n<!-- Chart section start -->\n<div id=\"chart-no-data\" style=\"text-align: center; color: rgba(0, 0, 0, 0.4); padding: 24px;\">No data</div>\n<div id=\"chart-content\" style=\"display: none; width: 100%;\">\n    <!--\n      Write the chart HTML here (no title etc.; only a suitable chart)\n    -->\n</div>\n<script>\n  window.renderChart = function(userAnswers, answerKeys) {\n    /*\n      Write logic here to render HTML from userAnswers and answerKeys; handle invalid data cases, e.g. 0 as a divisor\n    */\n  };\n</script>\n<!-- Chart section end -->"
    }
  ]
}
```

## Priority judgment principles

1. First recognize explicitly named question types (e.g. "maxdiff", "conjoint analysis", "dynamic table")
2. Judge the type by usage scenario and purpose (e.g. legal documents → signature; product configuration → conjoint; census → dynamic table)
3. When a need matches multiple types at once, prefer the most clearly matching one
4. One questionnaire can contain multiple types; judge each question by its own concrete need

## Key focuses

- Production-grade standards, fully functional
- Carefully crafted, pursue excellence
- Follow system constraints by default; when the user explicitly specifies a configuration, user configuration wins.
- Follow accessibility and format-validation requirements; ensure keyboard operability and visible errors.
- Custom question-type components (answer-side component and statistics chart) are embedded in the host page; component requirements:
  - No title, white background, iOS style, extreme performance
  - Output only the question body — no question title, confirm/submit buttons, explanatory text, selection hints, or preview
  - The outermost container of each custom question type must have empty spacing/background (background & margin & padding & border-radius: 0)

## Human-computer interaction spec

- Typography: choose beautiful, distinctive, recognizable fonts. Avoid generic fonts like Arial or Inter; pick fonts that elevate frontend visual quality, with personality and surprise. Pair a designed display font with a refined body font.
- Color & theme: before writing code, read survey-ui.css to learn the relevant default CSS variables and keep the overall style consistent.
- Motion: add animations for interactions and micro-interactions. Focus on high-impact moments: a well-orchestrated page-load animation with staggered timing (animation-delay) delights more than scattered micro-interactions. Use scroll-triggered and hover states to create surprises.
- Background & visual detail: create atmosphere and depth rather than defaulting to flat colors. Add ambient effects and textures matching the overall style, e.g. gradient grids, noise textures, geometric patterns, layered transparency, strong shadows, decorative borders, custom cursors, grain overlays, and other creative forms.
- Responsive: re-think appropriate interactions and re-layout for mobile.
- Coding standard: prefer open-source frontend components with GitHub Stars ≥ 500, or develop with native JS/CSS.
- CDN selection: prefer domestic mirrors (e.g. BootCDN, Staticfile, jsDelivr, etc.).
- Reliability: add network auto-detection for external requests in code, trying CDNs in order.
- Format validation: validate necessary controls and float error hints on invalid input in real time.
- Accessibility: keyboard operable, clear focus states, screen-reader readable (aria-label / role / value).

**Strictly avoid generic AI-generated aesthetics**, e.g. abusing font families (Inter, Roboto, Arial, system default fonts) or cliché color schemes (especially white backgrounds with purple gradients).

## Custom question type - answer-side component spec

If a dynamic item belongs to `UNBOUNDED_GENERIC`, `genericScript` only implements the current question's synchronous adapter and does not read cross-question answers; the answer must at least keep `itemKey`, the current label, source, the question type `typeValue`, and Runtime exposure. Follow the corresponding type's rule file for the concrete structure.

- Answer-side component max width on PC: 719
- Font size: 16px by default, allowed range 12–17px; font size >17px is forbidden
- Spacing: only the 4/8/12/16/24px set is allowed; large paddings/margins like 32px/48px are forbidden
- Input fields: height 40px; border-radius 12px
- Buttons/clickable items: height 44px; large radius (radius = half the height); 1px light dividers
- Dropdown select: native `<select> / <option>` is strictly forbidden; must use custom DOM + JS, without relying on browser system controls or default dropdown behavior.
- Tables: `td,th{border-color:#FFF};` table border-radius 12px
- Reuse the page's existing CSS tokens (variables) as much as possible; avoid inventing sizes, colors, or shadows
- Refer to iOS design guidelines unless the user explicitly asks for customization

### Reference docs per question type

- **Likert scale**
  - Keywords: "Likert", "matrix scale", "matrix single", "matrix choice", "table single", "table choice", "dimension", "liking"
  - Scenario: rating or selecting across multiple dimensions with explicit evaluation levels
  - Read file: `likert/rule.md`

- **NPS**
  - Keywords: "NPS", "Net Promoter Score", "would you recommend", "recommendation", "recommend to a friend"
  - Scenario: measuring users' recommendation willingness
  - Read file: `nps/rule.md`

- **CSAT**
  - Keywords: "CSAT", "satisfaction rating", "are you satisfied", "met expectations", "service rating"
  - Scenario: measuring immediate satisfaction with a specific product, service, or single interaction
  - Read file: `csat/rule.md`

- **CES**
  - Keywords: "CES", "effort", "ease", "smoothness", "convenience"
  - Scenario: measuring how easy it is for users to complete a specific task with a product/service
  - Read file: `ces/rule.md`

- **PMF**
  - Keywords: "PMF", "40% rule", "disappointment", "missing substitute", "indispensability"
  - Scenario: validating whether the product achieves product-market fit, assessing whether it has become users' "must-have"
  - Read file: `pmf/rule.md`

- **Weight/ratio**
  - Keywords: "weight", "proportion", "allocation", "total 100"
  - Scenario: allocating weight across multiple options/dimensions summing to a fixed value
  - Read file: `weight/rule.md`

- **Fill-in-the-blank**
  - Keywords: "fill in", "fill blank", "multi fill", "horizontal fill"
  - Scenario: collecting personal or text information (name, student ID, age, email, phone, address, etc.)
  - Read file: `fill-blank/rule.md`

- **Matrix fill**
  - Keywords: "matrix fill", "table fill"
  - Scenario: multi-field fill in table form
  - Read file: `matrix-fill/rule.md`

- **Dynamic table**
  - Keywords: "dynamic table", "family members", "multiple members", "submit multiple"
  - Scenario: collecting data with non-fixed row counts, supporting adding table rows via a button (e.g. family member info collection)
  - Read file: `dynamic-table/rule.md`

- **Date/time**
  - Keywords: "date", "time", "which day works", "appointment time", "when"
  - Scenario: selecting or entering a specific date or time
  - Read file: `datetime/rule.md`

- **Dropdown**
  - Keywords: "dropdown", "select box", "multi-select dropdown"
  - Scenario: when single/multiple choice questions have too many options
  - Read file: `dropdown/rule.md`

- **Multi-level select**
  - Keywords: "multi-level dropdown", "cascading select", "cascade selection", "multi-level options"
  - Scenario: generic cascading selection for **non-geographic** scenarios such as product categories, org structures, subject hierarchies
  - Read file: `cascade/rule.md`

- **Region**
  - Keywords: "region", "area", "province/city/district", "province-city cascade", "city"
  - Scenario: **geographic location** scenarios involving province/city/district, regions, dining areas, store locations, etc.
  - Read file: `region/rule.md`

- **Signature**
  - Keywords: "signature", "sign", "IOU", "contract", "agreement", "ensure legality"
  - Scenario: electronic signature confirmation, usually in legal documents, contracts, and agreements
  - Read file: `signature/rule.md`

- **Ranking**
  - Keywords: "ranking", "priority order", "arrange in order", "most preferred", "priority"
  - Scenario: ordering multiple options
  - Read file: `ranking/rule.md`

- **MaxDiff**
  - Keywords: "maxdiff", "maximum difference", "MaxDiff"
  - Scenario: measuring the relative preference strength across options
  - Read file: `maxdiff/rule.md`

- **Conjoint analysis**
  - Keywords: "conjoint", "conjoint query", "attribute combination", "parameter combination", "combination", "attribute", "level"
  - Scenario: generating combinations from multiple attributes (each with multiple levels) for users to choose from; product configuration and choice-preference analysis
  - Read file: `conjoint/rule.md`

- **Classification**
  - Keywords: "classification", "categorize", "group", "distinguish"
  - Scenario: classifying multiple items into specific categories
  - Read file: `classification/rule.md`

## Custom question type - custom statistics chart spec

### When to use
- When the questionnaire uses the GENERIC custom question type
- When writing the custom question type's statistics-chart code in the questionnaire schema (`genericQuestions > chartHtml`), use [references/question_schema.json](references/question_schema.json) for structure and [references/question_schema.example.json](references/question_schema.example.json) for an example.

### Rendering approach

Prefer the following components, including but not limited to:

| Technology | Suitable scenario |
|------|---------|
| **Chart.js** | Bar, line, pie, scatter, and other standard data charts |
| **SVG** | Flowcharts, architecture diagrams, diagrams, icons, geometric shapes |
| **D3.js** | Geographic maps (choropleth), complex data visualizations |
| **Pure HTML/CSS** | Dashboards, cards, forms, UI components, interactive controls |
| **Three.js** | 3D graphics (limited support, r128) |
| **Tone.js** | Audio/music generation |
| **React/JSX** | Component-based interfaces (another output mode) |

### Decision logic

Follow this decision chain to choose a technology:

```
User need
  ↓
Is it a data chart? → Chart.js
Is it a map?       → D3 + TopoJSON (pull real geographic data)
Is it a flow/structure diagram? → SVG (draw directly, no library)
Is it an interactive UI? → HTML + CSS + native JS
Is it 3D?          → Three.js
```

### Design constraints

- Chart width follows browser-window changes and re-renders
- Chart element layout is compact; use vertical space as much as possible
- Only use the predefined palette, assigned semantically; no rainbow colors
- All colors use CSS variables
- Font weights only 400/500, not 600/700 (too heavy, clashes with the host UI)
- No gradients, shadows, blurs, or other decorative effects; keep the flat style
- Chart caption text is not written into the HTML

### Hard limits

- No `localStorage` / `sessionStorage` (**only constrains the `chartHtml` chart code produced by this skill**; does not constrain the standard form's `survey-ui.js` business-logic region / same-machine base drafts)
- No `position: fixed`
- No emoji (use CSS shapes or SVG paths instead)
- When importing a CDN, must wait for the CDN to load before calling the render method
- When rendering special charts, the container must use a canvas tag; other tags are forbidden
- Chart width is 100%; dynamically adjusting width via JavaScript is forbidden
