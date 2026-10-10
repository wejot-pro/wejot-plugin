# Switching survey modes

Before switching, rebuild a spec from current artifacts so question meaning is not lost:

```bash
python survey-create/scripts/rebuild_spec_from_schema.py --workdir <survey-workspace> --locale <respondent-locale>
```

Edit the resulting draft, then run the target-mode generator. A mode switch rewrites the question region or complete HTML skeleton, so preserve custom presentation and restore it afterward. Successful validation removes temporary `*spec.json` drafts.

## Standard to free mode

1. Rebuild and verify the spec, especially `GENERIC` fields.
2. Generate the free skeleton:

   ```bash
   python survey-create/scripts/generate_free_mode_skeleton.py --spec <survey-workspace>/survey_spec.json --force --locale <respondent-locale>
   ```

3. Implement presentation in `survey-ui.css`, interaction in the custom region of `survey-ui.js`, and each generic question in its generic container. The generator does not inject generic source fields.
4. Preserve the bridge script, survey and question identity attributes, `buildAnswers()`, `submitSurvey()`, answer state, bindings, and custom-region markers.
5. Validate with `validate_free_mode_survey.py`.

After switching, standard-mode business logic belongs in its standard extension region and free-mode business logic belongs in its custom JS region. In either mode, preserve the bridge submission chain.
