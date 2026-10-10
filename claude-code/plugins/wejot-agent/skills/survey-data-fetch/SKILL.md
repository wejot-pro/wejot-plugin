---
name: survey-data-fetch
description: Retrieve real WeJot response data and its versioned metadata for analysis, reporting, or quality review. Never fabricate or silently reuse stale response data.
---

# Survey Data Fetch

Use when the user asks for response data, collection results, statistics, charts, reports, or any downstream task that depends on a WeJot survey's answers.

## WeJot data capabilities

| Step | Tool | Purpose |
|---|---|---|
| 0 | `getSurveyVersionOverview` | List versions and their submitted/valid counts when historical versions matter |
| 1 | `getSurveyChatPreview` | Inline question schema + `answer_sample` for structure profiling |
| 2 | `startSurveyResponseExport` | Start async wide-table CSV export; returns OSS URLs only |
| 3 | `pollSurveyResponseExport` | Poll subsequent batches and download each returned CSV reference |

Do **not** expect full answer rows in service responses. Let the host download each returned CSV reference with an available file-transfer capability.

When the user mentions previous versions, call `getSurveyVersionOverview(surveyCode)` first, then select versions with data for preview and export.

## Step 1 — Preview

Call `getSurveyChatPreview(surveyCode, version?)`.

- `version` omitted → latest version for the survey code.
- Record: `survey_id`, `survey_code`, `version`, `total_answer_count`, `has_answer_data`, `freshness`, `status`. Counts and schema refer to the selected version.
- Use `questions` and `answer_sample` to understand column semantics before analysis.
- `status=NO_QUESTIONS` or empty schema → stop; do not invent fields.

## Step 2 — Start export

Call `startSurveyResponseExport(surveyCode, version?, batch_size?, fetch_latest?)`.

- **`fetch_latest` defaults to `false`**: reuses an existing RUNNING/COMPLETED job when freshness matches.
- To force a fresh snapshot before analysis, **explicitly pass `fetch_latest=true`**.
- Record: `job_id`, `reused`, `total_answer_count`, `freshness`, `has_more`, `first_batch`.
- If `message` indicates no submitted responses (`total_answer_count=0`), treat as a valid empty result.

## Step 3 — Poll and download

While `has_more=true`, call `pollSurveyResponseExport(surveyCode, job_id, after_batch_no, limit?)`. Use the same `surveyCode` as in the start call.

- Download each batch from the returned `answers_csv.oss_url`; the response does not contain inline CSV.
- Format: **ORIGINAL wide-table CSV** (same as user export), not nested JSON answers arrays.
- Label local copies with `job_id`, `batch_no`, `serial_from`/`serial_to`, and `freshness.snapshot_at`.

## Retrieval contract

Record survey code, survey version, data freshness (`source_revision`, `snapshot_at`), total count, batch metadata, and download references. Downstream skills must use the newly fetched files and metadata — never prior chat claims or assumed local paths.

An empty result is valid. Never invent sample rows, counts, or fields.
