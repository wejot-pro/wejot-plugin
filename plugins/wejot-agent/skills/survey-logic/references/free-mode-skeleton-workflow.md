# Free-mode skeleton interaction contract

This local reference preserves the free-mode interaction constraints needed by `survey-logic`. Use the survey-authoring workflow supplied by the host to create or regenerate the base skeleton; this skill does not prescribe where its files are stored.

## Skeleton invariants

- Keep the HTML reference to the production `survey-bridge.js`.
- Keep the external `survey-ui.css` and `survey-ui.js` links.
- Keep the early `state` and `submitGenericAnswer` bootstrap used by parse-time generic scripts.
- Keep the survey root, every question's `data-question`, `data-code`, and `data-question-uuid`, `buildAnswers()`, `submitSurvey()`, the base answer state and event bindings, and the custom CSS/JS region markers.
- A generated skeleton has no visible submit button by default. Provide a visible, wired submission action.

## Immersive pagination contract

1. Pair every advance function with a visible control or event handler that calls it. A rendered “Next” button without a click binding is incomplete.
2. Only RADIO (8) may auto-advance immediately after writing its answer.
3. CHECKBOX (9), SCALE (10), MATRIX_SCALE (28), and multi-step GENERIC (39) require a visible “Next” or equivalent action.
4. Do not use failed final-submission validation as a substitute for page advancement.
5. Use `display: none` plus an explicit active state for one-question-per-page layouts. Put navigation in a fixed layer with an adequate stacking order or inside the active card; do not place it behind an absolutely positioned question card.
6. “Visible” means visible and clickable in the respondent state, not merely present in the DOM.
7. Under strict mode, declare every variable; an undeclared assignment can abort initialization and leave a blank question area.
8. Keep the page count synchronized with the current question count after additions, deletion, or reordering.

## Submission and in-form endings

For ordinary completion, keep the generated `submitSurvey()` and `buildAnswers()` chain. For an ending that must remain visible inside the questionnaire, follow [`submit-stay-pattern.md`](submit-stay-pattern.md): show the ending first, then persist through `SurveyDataBridge.submitAndStay({ answers: buildAnswers() })`.

Before delivery, verify that HTML, CSS, and JS selectors agree, an initial screen is visible, navigation is wired, and the submission action is reachable. Static syntax and schema validation do not replace this runtime closure check.
