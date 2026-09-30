# Custom answer-side language dict (--i18n-dict)

Use only when the questionnaire language is **not among the built-in 11 languages** (`zh-CN` / `zh-TW` / `zh-HK` / `en-US` / `es-MX` / `ja-JP` / `de-DE` / `fr-FR` / `id-ID` / `pt-BR` / `vi-VN`) and needs shell copy in that language, e.g. Korean `ko`.

## Usage

1. Create a JSON dictionary with an available deterministic JSON-writing capability:

   ```json
   { "ko": { "continue": "계속", "placeholder": "입력하세요", "other": "기타", "upload": "업로드" } }
   ```

   The full key list and Korean example are in `i18n-dict.example.json` in the same directory (54 keys); you may write only some keys.
2. Add the parameter when generating:

   ```bash
   python survey-create/scripts/generate_standard_survey.py --spec <survey-workspace>/survey_spec.json \
     --locale ko --i18n-dict <survey-workspace>/ko-i18n.json
   ```

   All generate/append/rebuild/assessment/exam scripts support `--i18n-dict`.

## Rules

- Provided keys use the custom copy; unprovided keys auto-fallback: non-Chinese languages → `en-US` (Chinese-family → `zh-CN`); no empty copy appears.
- Unknown keys are warned and ignored by the script (stderr hint).
- Only affects this run's dict merge; doesn't modify the main dict.
