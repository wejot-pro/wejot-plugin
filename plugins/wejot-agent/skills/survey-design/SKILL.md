---
name: survey-design
description: Turn an ambiguous survey or research idea into a methodologically sound, explicitly confirmed WeJot design brief before conventional-survey or AI-interview artifacts are generated.
---

# Survey Design

Use this skill when the user wants to create a survey, study, scale, or assessment but has not yet settled what to ask. This skill owns upstream research design; `survey-create` and `ai-interview-create` own artifact production after the design is confirmed.

Do not generate HTML, CSS, JavaScript, survey JSON, or production question components while the design is still being discussed. When the user's questions and structure are already explicit, skip directly to the appropriate production skill instead of forcing a design workshop.

## Method references

Read references progressively:

- Read [references/good-question.md](references/good-question.md) while defining the research question and boundaries.
- Read [references/design-framework.md](references/design-framework.md) before operationalizing objectives into constructs and indicators.
- Read [references/module-templates.md](references/module-templates.md) when building the questionnaire blueprint.
- Read [references/item-quality-checklist.md](references/item-quality-checklist.md) while drafting and reviewing individual questions.
- [references/methods.md](references/methods.md) is a compact cross-stage summary.

## Working state

Maintain a visible structured record in the conversation or in host-provided notes. Keep these states distinct:

- `empty`: not discussed yet.
- `draft`: proposed content still awaiting challenge or user confirmation.
- `confirmed`: explicitly accepted by the user.

Do not present a plausible generated draft as confirmed. Preserve settled decisions and do not repeatedly ask for information that is already known.

Ask one focused question at a time, or at most two tightly related questions in one round. Prefer selectable choices when the host can render them, but keep the workflow usable through ordinary conversation. Each round should update the relevant design record and identify what remains unresolved.

## Six-stage workflow

### 1. Research definition

Turn the initial topic into a genuine research question. Establish:

- background, trigger, and observed anomaly;
- the research question and contestable assumptions;
- two to five objectives, each with a stopping condition;
- target population, screening boundary, and explicit exclusions;
- business context, timing, sample, channel, duration, and material constraints;
- which objectives a questionnaire can answer and which require interviews, behavioral data, experiments, or secondary research.

Push back when the request is only a broad direction, assumes the answer, or reduces a complex decision to a yes/no question. Keep the research question as a draft until the user accepts its wording and boundaries.

### 2. Construct framework

Map every confirmed objective through `objective -> construct -> dimension -> indicator`. An indicator must be observable through a realistic respondent task and have a defined response scale or coding rule. If an objective has no measurable indicator, revise or remove it rather than inventing decorative questions.

Confirm that every objective is covered and that every proposed construct serves an objective before moving on.

### 3. Questionnaire blueprint

Choose or adapt an appropriate module skeleton. Record module order, module purpose, estimated question count, expected duration, respondent flow, and the rationale for ordering. Unless the study demands otherwise, use a funnel from eligibility and concrete behavior toward attitudes, sensitive questions, and demographics.

Treat this as a major user review point. Do not begin item drafting until the blueprint is confirmed.

### 4. Module questions

Draft one module at a time. For each item specify its objective or indicator, respondent-facing wording, question type, options or scale, requiredness, relevant recall window, and any uncertainty still needing review.

After each module, stop for user review before drafting the next one. Do not let a preferred component determine the research design; choose a standard or custom type only after the answer task is clear.

### 5. Review and confirmation

Review the complete design for objective coverage, respondent burden, ordering, ambiguous terminology, leading or double-barrelled wording, hidden assumptions, scale balance, exhaustive options, sensitive-item placement, and duration. Record unresolved risks and what the survey cannot establish.

Generation remains blocked until the user explicitly confirms the complete design brief.

### 6. Delivery

Produce a structured handoff containing the confirmed research question, objectives and stopping conditions, audience and exclusions, construct map, module blueprint, item drafts, expected duration, unresolved risks, and intended production skill.

- Use `survey-create` for a conventional standard/free-mode survey.
- Use `ai-interview-create` for an AI, voice, conversational, or interview-style study.

The production skill may resolve safe implementation details, but it must not silently change confirmed research semantics.
