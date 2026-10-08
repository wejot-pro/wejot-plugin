---
name: survey-create
description: Create or revise conventional WeJot standard/free-mode survey drafts with bundled templates, data rules, optional generators, and the host-driven version lifecycle. Route AI interviews and specialized GENERIC components to their dedicated skills.
---

# Survey Create

Turn the user's research brief into a Java-persistable conventional survey draft. This skill package ships the templates, references, and optional local scripts needed to produce the required four-artifact bundle. The shared lifecycle in `wejot-authoring-lifecycle` owns project state and publication.

## Skill package layout

| Path | Purpose |
|---|---|
| `templates/` | HTML/CSS/JS baselines and JSON schema templates (`survey-unified-sample.html`, `survey-ui.css`, `survey-ui.js`, `question_schema.json`, …) |
| `references/` | Data rules, spec schema, scene playbooks (`data_rules.md`, `minimal_survey_spec.json`, `stepsPerScene/`, exam/assessment patterns) |
| `scripts/` | Optional local generators/validators when the host can run Python 3 |

Required artifact basenames (the host chooses where to materialize the editable draft):

- `survey-unified-generate.html`, `survey-ui.css`, `survey-ui.js`, `question_schema_generate.json`

HTML must reference `./survey-ui.css` and `./survey-ui.js`. `survey-bridge.js` stays on the production CDN URL in HTML; consult the bundled read-only `templates/survey-bridge.js` only when a runtime API detail is needed.

## Authoring lifecycle

1. Let the host establish or reopen the project with `createOrOpenSession`; retain the returned session, baseline version, and exact editor handoff.
2. For an existing survey, let the host call `getLatestSurveyAssets` before editing and materialize the returned bundle manifest in an available workspace. Verify the declared hash and size. A returned `survey_version=0` means there is no persisted draft yet.
3. Create or edit using templates, references, and optional scripts below.
4. `GENERIC` requirements → load `survey-components` first. Cross-question runtime behavior → `survey-logic`.
5. When Python is available, run the applicable local validator (`validate_standard_survey.py` or `validate_free_mode_survey.py`) and fix blocking issues.
6. Submit only on explicit user request. Immediately before submit, let the host re-check the latest version without pulling over the edited draft. Package exactly the four required basenames, compute the bundle SHA-256 as lowercase hexadecimal plus its positive byte size, then let the host call `prepareSubmitBundleUpload`, perform the returned upload instruction with the unchanged bundle, and call `submitSurveyArtifacts` with the same manifest.
7. Verify the returned new version and use the exact editor handoff returned by the service. Do not download the post-submit bundle over the just-submitted local files.

Never overwrite an existing local draft during pull without first reporting the conflict and obtaining explicit user approval. Keep the returned `survey_version` as `base_version`. The optional header image is submitted separately from the four-file ZIP; keep the HTML cover reference consistent with it.

## Question types

Standard: `RADIO` (8), `CHECKBOX` (9), `TEXTAREA` (1), `UPLOAD` (15), `SCALE` (10), `MATRIX_SCALE` (28). Custom: `GENERIC` (39) when standard types cannot express the interaction.

- **Standard mode**: fill GENERIC fields in spec; `scripts/generate_standard_survey.py` assembles HTML.
- **Free mode**: spec drives schema + placeholder; implement `genericHtml`/`genericScript`/`genericStyle` in workspace CSS/JS (see `references/stepsPerScene/F2.md`).

## Standard vs free mode

| Dimension | Standard | Free |
|---|---|---|
| HTML marker | no `data-survey-mode="free"` | `data-survey-mode="free"` |
| Generator | `scripts/generate_standard_survey.py` | `scripts/generate_free_mode_skeleton.py` |
| Style/runtime | `survey-ui.css` + `survey-ui.js` base + extension region | edit LLM regions in CSS/JS |
| Validator | `scripts/validate_standard_survey.py` | `scripts/validate_free_mode_survey.py` |
| Append | `scripts/append_questions_to_survey.py` | `scripts/append_questions_to_free_mode_survey.py` |
| Same-device draft | Enabled by the bundled template; set `SURVEY_LOCAL_DRAFT_DEFAULT=false` to disable answers + breakpoint restoration | Answers restored by default; restoring the page requires the optional free-mode hook |

## Respondent-side language

Question and option wording comes from the authored spec. For a non-`zh-CN` questionnaire, pass `--locale <language>` so fixed shell copy—buttons, validation messages, page labels, Other, upload copy, placeholders, and completion text—uses the same language.

The built-in platform locales are `zh-CN`, `zh-TW`, `zh-HK`, `en-US`, `es-MX`, `ja-JP`, `de-DE`, `fr-FR`, `id-ID`, `pt-BR`, and `vi-VN`. Read [references/i18n-locale.md](references/i18n-locale.md) before generating a non-default locale. For another locale, also read [references/i18n-dict.md](references/i18n-dict.md) and start from [references/i18n-dict.example.json](references/i18n-dict.example.json).

## Mode detection

If both `survey-unified-generate.html` and `question_schema_generate.json` exist in `<survey-workspace>`:

- **FREE** when HTML contains `data-survey-mode="free"` (or legacy free CSS marker).
- **STANDARD** otherwise.
- **CREATE** when either file is missing.

## Creation decisions

Before creating a new survey, inspect the whole request and identify every unresolved decision that materially changes the output. Ask those known questions together through an interaction method available to the host; do not drip-feed one predictable question per turn. Ask a later follow-up only when an earlier answer creates a genuinely new branch that could not have been expressed beforehand.

When the supplied material is sufficient, first produce a structurally valid standard-mode base preview so the user can evaluate real content instead of an abstract mode label. Treat that preview as provisional. If the user did not choose a mode and the choice still matters, explain the practical trade-offs among standard, free, exam, assessment, and AI interview forms, then obtain one choice before investing in mode-specific styling, scoring, or interaction. When the material is insufficient even for a responsible base preview, include the missing content decisions in the initial question batch. Do not ask about implementation details the authoring agent can decide safely.

- Standard: fastest and most stable for ordinary fixed question types and common branching; less visual freedom.
- Free: greatest layout and interaction freedom; not a default excuse to build a complex scoring engine in the questionnaire.
- Exam: objective scoring with a simple result path.
- Assessment: respondent-facing profile, band, score, or share result using the bundled pattern.
- AI interview: conversational or voice-led research with structured and open interview questions; route immediately to `ai-interview-create`.

When the user already says interview survey, AI interview, voice interview, conversational interview, or interview outline, skip the conventional mode question and use `ai-interview-create`.

## Scene routing

After mode is known, **read** the matching playbook under `references/stepsPerScene/` (do not guess steps):

| Scene | Playbook |
|---|---|
| Standard create / full refresh | `references/stepsPerScene/S1.md` |
| Standard append questions | `S2.md` |
| Standard edit title/delete/reorder | `S3.md` |
| Standard non-question DOM | `S4.md` |
| Free create / skeleton refresh | `F1.md` |
| Free style/interaction | `F2.md` |
| Free append | `F3.md` |
| Free edit title/delete/reorder | `F4.md` |
| Free non-question DOM | `F5.md` |
| Standard → free switch | `MODE_SWITCH.md` |
| Exam scoring | `references/exam-pattern.md` + `scripts/generate_exam.py` |
| Assessment / eval share | `references/assessment-pattern.md` + `scripts/generate_assessment.py` |
| Header image | `references/header-image.md` (optional submission metadata + matching HTML cover) |

`AI_INTERVIEW` requests → stop and use `ai-interview-create`.

## Creating from empty workspace

1. Copy baselines from `templates/` into `<survey-workspace>` when generators have not run yet: at minimum `survey-ui.css` and `survey-ui.js` for standard mode.
2. Read `references/data_rules.md` (standard) or `references/data-rules-free.md` (free).
3. Draft `survey_spec.json` bound to `references/minimal_survey_spec.json` (example: `minimal_survey_spec.example.json` — structure only, never copy business UUIDs).
4. Run the mode-appropriate generator from `scripts/` with `--spec` pointing at `<survey-workspace>/survey_spec.json`, the respondent-side `--locale`, and output directed to `<survey-workspace>`.
5. If Python is unavailable, hand-edit the four workspace files to the same rules, then proceed to submit when the user approves.

## Validation (dual gate)

**Local (optional, when Python available)** — run from `<survey-workspace>`:

```bash
python survey-create/scripts/validate_standard_survey.py --dir <survey-workspace>
python survey-create/scripts/validate_free_mode_survey.py --schema <survey-workspace>/question_schema_generate.json --html <survey-workspace>/survey-unified-generate.html --dir <survey-workspace>
```

**Publication (required only on user request)** — use the host-driven lifecycle above. `prepareSubmitBundleUpload` checks the baseline before accepting an upload instruction; `submitSurveyArtifacts` downloads the staged bundle, verifies its size and SHA-256, requires exactly the four artifact basenames, validates HTML/JSON, and creates the new survey version. Local validation is preflight; service-side validation is part of submission.

## Data rules and templates (fallback)

When scripts fail repeatedly, read directly:

- `templates/question_schema.json` + `templates/question_schema.example.json`
- `templates/survey-unified-sample.html`
- `references/data_rules.md`

Ensure HTML question count matches JSON buckets and pagination page numbers remain aligned with the DOM.

In free mode, every `data-page-break` must be carried by an independent `.pb` direct child of the `[data-survey-role="survey"]` root, at the same level as question nodes or slides. Never put it on a question, slide, option container, question-content container, or any container that holds question content. The page-number set on questions must equal the page-number set on page breaks, and each question must appear after its own page break and before the next one. `data-page-break-id`, when needed, belongs only on the independent page-break node.

For `UPLOAD`, `maxFileCount` and `maxFileSize` are per-question constraints supported by the generator and runtime. Use positive values justified by the requirement; when unspecified, use the generator defaults of one file and 102400 KB. Do not replace an explicit supported limit with a different guessed limit.

## Scoring / analysis split

Survey surface collects answers; heavy post-hoc scoring belongs in `data-analysis` after samples exist. Do not build full scoring engines in `survey-ui.js` unless the user explicitly chose exam/assessment patterns.

## Invariants

- One session → one active survey.
- Do not fabricate unsupported schema fields or host capabilities.
- Keep private transport and deployment implementation details outside artifacts and skill instructions.
- On version, lock, validation, or persistence errors, follow `wejot-authoring-lifecycle`.

## Persist answers and stay in the survey

When the user wants to collect or submit answers and then remain inside the survey to show a thank-you page, result summary, poster, or ending screen, read `references/submit-stay-pattern.md` first and follow its `SurveyDataBridge.submitAndStay(...)` flow. Do not drive this experience through a normal submission entry point that redirects to the host completion page.
