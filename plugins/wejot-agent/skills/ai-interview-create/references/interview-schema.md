# AI Interview JSON Guide

Use this guide together with [interview_schema.json](./interview_schema.json), which is the complete schema bundled inside this skill. Do not invent fields that are absent from that schema.

## Survey metadata

Required concepts:

- `kind`: `AI_INTERVIEW`
- `title`, `description`
- `welcomeMessage`, `outroMessage`
- `language`
- allowed interaction modes and one default mode

Optional concepts include media mode, recording choices, keyboard input, brand information, interview background, and moderator requirements. Include them only when supported and relevant. Recording settings must reflect explicit product and consent requirements.

## Question groups

The prototype groups questions by type:

- `radioQuestions`: fixed single choice
- `textQuestions`: short structured text input (`type: INPUT`)
- `checkboxQuestions`: fixed multiple choice, with optional minimum and maximum
- `scaleQuestions`: one score for one object; use `options` containing `sort`, `score`, and `title`
- `matrixScaleQuestions`: several dimensions scored on one shared scale; use `rows` and `columns`
- `uploadQuestions`: file requirements and limits only when public upload support exists
- `interviewQuestions`: open discussion led by the AI moderator
- `interactiveQuestions`: visual or structured interview interactions

Each question needs a participant-facing title, stable UUID, type, integer required flag, sort order, moderator guide, and follow-up settings. It may include description and condition. Choice options need stable order and labels. Preserve existing UUIDs during edits; let the bundled generator create UUIDs only for new questions that omit them.

## Follow-up

Represent follow-up as one canonical object supported by the current schema. The prototype modes are `none`, `one`, `two_three`, `open`, and `logic`. For `logic`, include a precise prompt defining triggers, useful evidence, sensitive topics to avoid, and a stopping condition. Do not emit legacy alias fields unless the server schema explicitly requires compatibility.

## Checks

- Default mode is included in allowed modes.
- UUIDs and sort positions are unique.
- Conditions refer to existing identifiers and reachable answers.
- Structured options and scales are nonempty and ordered.
- Every interview question has an appropriate follow-up mode.
- Unsupported attachment, recording, or media capabilities are omitted rather than simulated.
