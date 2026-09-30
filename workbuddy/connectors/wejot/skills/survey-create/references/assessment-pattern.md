# Configuration-driven assessment surveys

An assessment shows a personalized type, score, profile, and recommendations after the respondent finishes. Generate it in two stages; do not hand-build the result page, scoring, persistence, copy action, or poster unless the configuration-driven implementation cannot express the request.

## Generation

1. Create a valid `survey_spec.json` with one `questions` array.
2. Run:

   ```bash
   python generate_free_mode_skeleton.py --spec <survey-workspace>/survey_spec.json --output-dir <survey-workspace>
   ```

3. Create `eval_config.json`, using `eval_config.example.json` as the structural reference.
4. Run:

   ```bash
   python generate_assessment.py --html <survey-workspace>/survey-unified-generate.html --config <survey-workspace>/eval_config.json
   ```

The second step injects the intro, result page, step navigation, scoring, no-redirect persistence, copy/share behavior, poster, QR code, and default assessment styles.

## Configuration

```json
{
  "intro": { "title": "Assessment", "sub": "Five questions", "chips": ["Type A", "Type B"] },
  "model": "dimension",
  "scoring": { "Q1": { "1": "type_a", "2": "type_b" } },
  "types": {
    "type_a": {
      "emoji": "A",
      "title": "Type A",
      "label": "Short label",
      "desc": "Profile summary",
      "sections": { "Strengths": "...", "Risks": "...", "Next steps": "..." }
    }
  },
  "sectionOrder": ["Strengths", "Risks", "Next steps"]
}
```

- `dimension` gives each selected option a type key and returns the most-voted type.
- `sum` gives options numeric scores and resolves the total through ascending `bands[].max` thresholds.
- `scoring` keys are question codes; option keys are one-based index strings.
- Section names must match `sectionOrder`.

The result must appear inside the survey before no-redirect persistence. A redirecting submit hides the survey frame, so assessment generation uses `submitAndStay` and writes a string `eval_result`: a numeric string for `sum`, or the selected type title for `dimension`.

Verify valid JSON, run the complete intro-to-result flow, confirm scoring mappings, and ensure the generated assessment suite owns persistence and sharing.
