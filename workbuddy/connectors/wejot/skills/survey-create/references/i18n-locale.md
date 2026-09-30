# Answer-side language (--locale)

## Purpose

The questionnaire content language (questions, options, descriptions) is determined by the spec; `--locale` only controls the answer-side **fixed shell copy**: submit/continue buttons, validation hints, pagination, Other option, upload button, input placeholders, and `survey-ui.js` runtime copy.

## Language list

The 11 languages aligned with the platform/website: `zh-CN` / `zh-TW` / `zh-HK` / `en-US` / `es-MX` / `ja-JP` / `de-DE` / `fr-FR` / `id-ID` / `pt-BR` / `vi-VN`; use the current questionnaire/user's answer-side language. Unbuilt languages auto-fallback: Chinese-family → `zh-CN`, others → `en-US`; no Chinese shell copy is generated.

All generate/append/rebuild/assessment/exam scripts accept `--locale` (command examples in `stepsPerScene/S1.md` and other scene docs).

## Semantic copy

**Semantic copy** for non-zh-CN questionnaires (e.g. scale labels `scaleLabels`, input placeholders) must be written in the spec in the target language; script fallback values only take effect when missing.

## Platform-unsupported languages (e.g. Korean)

Pass an extra language dict JSON with `--i18n-dict {file}` (`{locale: {key: value}}`); you may write only some keys; unprovided keys auto-fallback to `en-US`; the key list and Korean example are in `i18n-dict.example.json`; full explanation in `i18n-dict.md`. When the script hits an unbuilt language without this parameter, it warns on stderr.
