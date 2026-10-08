---
name: ai-interview-create
description: Create or revise a WeJot AI interview, voice interview, conversational interview, interview outline, or interview-style study as an AI_INTERVIEW schema rather than a conventional HTML questionnaire.
---

# AI Interview Create

Use this skill whenever the request is an interview survey, AI interview, voice interview, conversational interview, interview outline, interview questions, or interview-style research—even when the user does not explicitly say “AI”. Do not route such requests through ordinary survey-create.

An AI interview is a distinct survey form. question_schema_generate.json is the primary authored source. The platform interview host owns voice/chat presentation, microphone or camera behavior, recording, live probing, cards, and the ending experience. Do not hand-build those experiences as a conventional questionnaire UI.

Read before constructing or reviewing the schema:

- [references/interview-schema.md](references/interview-schema.md) for the portable field guide.
- [references/interview_schema.json](references/interview_schema.json) for the complete structural contract.

The included scripts/generate_interview_survey.py normalizes the schema and derives the required lightweight HTML/CSS/JS companions; scripts/validate_interview_survey.py validates a manually edited draft. Run them against the host-selected draft workspace. The resulting publication bundle still follows `wejot-authoring-lifecycle`.

## Pull and regeneration contract

The service promises `question_schema_generate.json` as the persisted authoring source for an AI interview. HTML, CSS, and JS are derived companions, not independent remote sources of truth.

- After a pull, inspect the JSON first and confirm `survey.kind` is `AI_INTERVIEW`.
- Empty pulled CSS or JS is normal for an AI interview. Do not report it as corruption, borrow traditional-survey assets, or hand-fill placeholders.
- Treat pulled HTML as a derived companion as well; do not use it to override newer service-normalized JSON.
- Before preview, validation, or submission, run scripts/generate_interview_survey.py from the pulled or edited JSON. The generator must recreate and validate the complete four-artifact draft.
- Service-normalized survey metadata in the pulled JSON is the new baseline. Preserve it during a targeted edit unless the user explicitly asks to change that metadata.

## Schema invariants

- Set survey.kind to AI_INTERVIEW.
- Use these root arrays once each as needed: textQuestions, radioQuestions, checkboxQuestions, scaleQuestions, matrixScaleQuestions, uploadQuestions, interviewQuestions, and interactiveQuestions.
- Do not use a root questions array, schemaVersion, or hand-authored question id/code.
- Every question needs a stable uuid, type, sort, title, requiredness, interviewer guide, and follow-up policy. The generator may create a missing UUID for a new question; preserve existing UUIDs during edits.
- Use integer 0/1 where the schema defines flags.
- Keep participant-facing wording separate from interviewer guidance.
- The Java publication service requires a non-empty HTML companion that references survey-ui.css and survey-ui.js; use the generator rather than inventing placeholder bodies.

## Question types

| Type | Root array | Use |
|---|---|---|
| INPUT | textQuestions | Short structured text such as role, age, or contact field |
| RADIO | radioQuestions | One fixed choice |
| CHECKBOX | checkboxQuestions | Multiple fixed choices |
| SCALE | scaleQuestions | One score for one object |
| MATRIX_SCALE | matrixScaleQuestions | The same scale applied to several rows or dimensions |
| UPLOAD | uploadQuestions | Evidence, screenshot, document, or other file |
| INTERVIEW | interviewQuestions | Open discussion with optional probing |
| INTERACTIVE | interactiveQuestions | Camera, visual demonstration, object viewing, or another genuinely interactive task |

For RADIO and CHECKBOX, options use stable ordered labels; enable an “other” response only when needed. For SCALE, use ordered options with sort, score, and title. For MATRIX_SCALE, put dimensions in rows and the shared scale in columns. Never disguise a multi-dimensional matrix as one SCALE question whose dimensions exist only in guide.

## Interview design

- Unless the user explicitly wants a purely open qualitative interview, balance structured questions with open interview questions so results remain comparable across participants.
- Use structured types for screening, attributes, preferences, constraints, choices, and ratings.
- Use INTERVIEW for “why”, “how”, experience narratives, and exploratory follow-up.
- Use INTERACTIVE only when visual or real-time interaction materially helps.
- A short 3–6 question interview with measurable preferences or constraints should normally contain at least one structured question.
- Respect an explicitly requested question count.

## Guide and follow-up alignment

The host renders structured cards from schema fields while the interviewer speaks from guide; those two sources must ask for the same answer.

- A SCALE guide asks for one score about the one object represented by the question.
- A MATRIX_SCALE guide explains how to score the rows already present in schema; it does not introduce extra dimensions.
- A choice-question guide follows the declared options and does not invent a second option list.
- Open interview and interactive questions may place probing directions in guide and followup.logicPrompt.

Use follow-up modes intentionally: none, one, two_three, open, or logic. Structured questions normally use none. Logic-based probing must state the evidence that triggers a probe and the condition for stopping. Interactive questions generally use two_three unless the task truly requires no verbal exploration.

## Survey-level defaults

Infer ordinary product details rather than delaying a well-specified request:

- Keep participant-visible description and welcomeMessage in the survey language, and end the welcome by asking whether the participant is ready.
- Write a participant-visible outroMessage that thanks them and clearly ends the interview.
- Match language to the request (zh-CN for Chinese unless otherwise requested).
- Default to allowing phone and chat with phone as the default. Derive mediaMode from the chosen mode and recording settings.
- Preserve existing recording, input, brand, mode, language, and message fields during targeted edits. Do not invent a logo location.
- Summarize the research context in background and keep requirements neutral, concise, and focused on actionable insight.

## Create and edit workflow

1. Let the host establish or pull the current project through `wejot-authoring-lifecycle`.
2. For a new interview, build the schema from the user’s topic, objectives, question count, and explicit constraints using the internal references above.
3. For an existing interview, start from the pulled JSON even when its CSS or JS companions are empty. Patch only the requested fields. Preserve UUIDs, sort order, types, requiredness, conditions, follow-up policies, modes, recording settings, service-normalized metadata, and other non-target fields unless the user asks to redesign them.
4. Run generate_interview_survey.py against the draft workspace to normalize the JSON and regenerate HTML, CSS, and JS. If a generated companion was then manually edited without regeneration, run validate_interview_survey.py.
5. Resolve every validation error. Submit only when the user explicitly requests publication, using the host-driven version workflow and the newly generated four-artifact bundle. After success, complete the editor handoff in `wejot-authoring-lifecycle`.

Do not rewrite an existing schema wholesale for a translation, wording change, title edit, or other narrow request. Whole-schema redesign is appropriate only for a new interview or an explicitly requested structural redesign.
