---
name: wejot-authoring-lifecycle
description: Preserve the shared WeJot project, pull, local-edit, version-check, upload, and publication lifecycle after the current host has connected the WeJot MCP server.
---

# WeJot Authoring Lifecycle

Use this skill after the current host has loaded and authenticated the WeJot MCP server. Use it for project recovery, survey switching, version conflicts, locks, or submission failures. It defines the shared authoring lifecycle; installation and authentication belong to the current host adapter, while questionnaire content belongs to `survey-create` or `ai-interview-create`.

## Core state model

- One WeJot session owns one active survey project. Keep `session_id`, survey identity, and `survey_version` distinct.
- For a traditional survey, the latest remote artifact bundle is the persisted source of truth. For an AI interview, `question_schema_generate.json` is the only persisted authoring source promised by the service; HTML, CSS, and JS are derived local companions. A local draft is editable working state and is not published until an explicitly approved submission succeeds.
- `base_version` is the remote version from which the local draft was derived. Obtain it from the service; never invent a local version counter.
- Pull the latest version before editing. Immediately before submission, check the latest version again without overwriting the edited draft.
- A version mismatch is a merge problem, not a retry problem: preserve both versions, reconcile the substantive differences, then submit against the new baseline.
- Use the exact editor handoff returned by the service. Do not infer or construct an editor location.

## Host-driven lifecycle

The host owns all service interaction. Skills and helper scripts may prepare or validate local artifacts, but they do not establish their own service connection.

1. Establish or reopen the survey project with `createOrOpenSession`.
2. Fetch current metadata and the artifact-bundle manifest with `getLatestSurveyAssets`.
3. Let the host materialize that bundle in an available local workspace, verify its declared SHA-256 and byte size, and keep the returned survey version as `base_version`.
   - Inspect `question_schema_generate.json` before judging the companion files.
   - For a traditional survey, treat missing or unexpectedly empty required artifacts as a pull failure.
   - If `survey.kind` is `AI_INTERVIEW`, treat the JSON as canonical. Empty CSS or JS is a normal service response, not data loss or a reason to reject the pull. Route the draft through `ai-interview-create` so its generator reconstructs HTML, CSS, and JS before preview, validation, or submission.
4. Edit and locally validate the draft. Local writes and successful local validation do not imply publication.
5. Submit only after the user explicitly requests publication:
   - deterministically package exactly the required four artifacts;
   - compute the bundle SHA-256 as 64 lowercase hexadecimal characters and record the positive byte size;
   - call `prepareSubmitBundleUpload` with the current session, baseline, and bundle manifest;
   - let the host upload the unchanged bundle using the returned upload instruction;
   - call `submitSurveyArtifacts` with the same session, baseline, hash, size, and optional header image.
6. Treat `submitSurveyArtifacts.success=true` and the returned new version as the publication boundary. Fetch metadata afterward only to verify the result; do not overwrite the just-submitted local draft.

The Java service requires the bundle to contain exactly these basenames at archive root: `survey-unified-generate.html`, `survey-ui.css`, `survey-ui.js`, and `question_schema_generate.json`. HTML must reference `survey-ui.css` and `survey-ui.js`. The service validates the bundle during submission; there is no separate public artifact-validation tool. Local validators are therefore useful preflight checks, not substitutes for the submission gate.

## Traditional survey versus voice interview

- Use `survey-create` for conventional respondent-driven questionnaires: standard or free-mode pages, fixed question cards, custom `GENERIC` components, branching, exams, and assessments.
- Use `ai-interview-create` when the request is an AI interview, voice interview, conversational interview, interview outline, or interview-style research. Its JSON is the only persisted authoring source promised by the service; the platform interview host owns voice/chat presentation, recording behavior, probing, and the interview runtime. Pulled CSS or JS may be empty and must be regenerated rather than repaired by hand.
- Both forms use the same host-driven session/version lifecycle and the same four-artifact submission boundary. For AI interviews, that boundary contains the canonical JSON plus generated companions; it does not make those companions independent persisted sources. Do not turn an AI interview into a hand-built traditional HTML questionnaire.

## Failure handling

- Project missing or inaccessible: stop and report the affected project; do not probe other projects.
- Version conflict: fetch the latest metadata and bundle, preserve the local draft, reconcile, and submit again only after the merged result is understood.
- Survey locked: report the supplied reason and stop; do not bypass product locks.
- Invalid artifact or validation failure: fix the reported artifact/schema problems and retain the same baseline unless the remote version changed.
- Retryable transport or persistence failure: retry only the identical bundle within a bounded host workflow. Check current state before deciding another write is needed.
- Non-retryable persistence failure: stop and report it. Never claim a version was published without a successful service result.

Keep private transport and deployment implementation details outside skills and survey artifacts.
