# Configuration-driven exam surveys

An exam calculates a score and stores a single string in `eval_result`. It may show the result to the respondent or show only an in-survey thank-you page. Use the two-stage workflow below; it already includes the free-mode skeleton step.

## Generation

1. Create valid `survey_spec.json` with one `questions` array.
2. Run `generate_free_mode_skeleton.py --spec <survey-workspace>/survey_spec.json --output-dir <survey-workspace>`.
3. Create `exam_config.json` from `exam_config.example.json` for additive scoring or `exam_config.example.rules.json` for combined rules.
4. Run `generate_exam.py --html <survey-workspace>/survey-unified-generate.html --config <survey-workspace>/exam_config.json`.

The exam generator injects the intro, scoring, scroll or step layout, result or thank-you view, and no-redirect persistence. It does not inject assessment sharing or posters.

```json
{
  "intro": {
    "title": "Exam title",
    "sub": "Optional subtitle",
    "notices": ["Read each question carefully"],
    "chips": ["Automatically scored objective questions"],
    "image": "",
    "cta": "Start exam",
    "enabled": true
  },
  "display": {
    "layout": "scroll",
    "showResultToUser": true,
    "thanksText": "Thank you. Your response was submitted."
  },
  "scoring": {
    "model": "sum",
    "autoExcludeTypes": ["TEXTAREA", "UPLOAD"],
    "excludeQuestionCodes": [],
    "maxScore": 150,
    "mapping": { "Q1": { "1": 0, "2": 2, "3": 0 } }
  },
  "grades": [{ "min": 60, "label": "Pass" }],
  "evalResult": { "format": "score" }
}
```

The intro is enabled by default. If omitted, its title comes from the survey spec and notices are generated from the question and scoring configuration. A non-empty notices array is used verbatim; `null` or an absent key requests automatic notices; an empty array explicitly suppresses notices. Keep respondent-facing copy free of administrative instructions.

`display.layout` is `scroll` or `step`. `showResultToUser: false` shows only the thank-you page.

Use `sum` with question codes and one-based option indexes for radio questions and independently scored checkbox options. Use `rules` only for supported multi-question combinations. Never invent option-level codes such as `Q1_opt_1`.

Current rules include `everyAllOptionsSelected`, `countAllOptionsSelected`, `everyNoneSelected`, and `default`; first match wins. `everyAllOptionsSelected` means every option, including distractors, so it cannot express an exact correct subset. Prefer `sum` for mixed surveys unless a real cross-question combination is required.

`evalResult.format` may be `score`, `scoreMax`, or `grade`. Text and upload questions are excluded from automatic scoring by default but their answers are still collected. Add other unscored questions to `excludeQuestionCodes`. Explain that writing or uploads require manual grading if the user expects them to affect the score.

Regenerate after changing the config; do not hand-edit the injected exam block. The injected suite sets `window.__WJ_EVAL_RESULT__`, displays the in-survey result or thanks, and persists through `submitAndStay`.

Verify both JSON files, header-image consistency when used, the complete intro-to-ending flow, the stored `eval_result`, and collection of excluded question answers.
