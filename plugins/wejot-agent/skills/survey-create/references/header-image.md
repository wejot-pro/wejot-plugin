# Header image consistency

The header image is optional submission metadata rather than a member of the four-artifact ZIP. The host may keep that value in any suitable draft state; this skill does not prescribe a local storage path.

When a draft has a header image:

1. Keep the submitted header_image value and the visible cover image in survey-unified-generate.html equal.
2. Preserve the current value during unrelated edits.
3. When the user requests a replacement, update both the submission metadata and the HTML cover reference.
4. If the user did not request a custom image, retain the existing or template default. Do not invent an unavailable local resource or a dedicated header-image service operation.

Pass the optional header_image value to submitSurveyArtifacts. A header-only change still requires explicit user approval and the normal version-aware submission lifecycle, but it does not require regenerating every question artifact.
