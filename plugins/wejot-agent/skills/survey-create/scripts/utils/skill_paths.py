"""Paths for survey-create skill package (templates, references, scripts).

Scripts resolve skill assets relative to this file, not the host sandbox.
Survey artifact output always goes to the host workspace (--dir / cwd).
"""

from __future__ import annotations

from pathlib import Path

# shared/skills/survey-create/
SKILL_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = SKILL_ROOT / "templates"
REFERENCES_DIR = SKILL_ROOT / "references"
SCRIPTS_DIR = SKILL_ROOT / "scripts"
ASSETS_DIR = SCRIPTS_DIR / "assets"

# Template files (copied into host workspace on create)
TEMPLATE_HTML_SAMPLE = TEMPLATES_DIR / "survey-unified-sample.html"
TEMPLATE_SURVEY_UI_CSS = TEMPLATES_DIR / "survey-ui.css"
TEMPLATE_SURVEY_UI_JS = TEMPLATES_DIR / "survey-ui.js"
TEMPLATE_QUESTION_DEFAULTS = TEMPLATES_DIR / "question_defaults.json"
TEMPLATE_QUESTION_SCHEMA = TEMPLATES_DIR / "question_schema.json"
TEMPLATE_SURVEY_BRIDGE_JS = TEMPLATES_DIR / "survey-bridge.js"

# Backward-compatible aliases (used by generators)
SYSTEM_QUESTIONARE_TEMPLATES_DIR = TEMPLATES_DIR
SYSTEM_QUESTION_DEFAULTS_PATH = TEMPLATE_QUESTION_DEFAULTS
LEGACY_SYSTEM_JSON_TEMPLATE_PATH = TEMPLATE_QUESTION_SCHEMA
SYSTEM_HTML_TEMPLATE_PATH = TEMPLATE_HTML_SAMPLE
SYSTEM_SURVEY_UI_JS_PATH = TEMPLATE_SURVEY_UI_JS
SYSTEM_SURVEY_UI_CSS_PATH = TEMPLATE_SURVEY_UI_CSS

# Reference specs used by generators/validators
MINIMAL_SPEC_TEMPLATE_PATH = REFERENCES_DIR / "minimal_survey_spec.json"
MINIMAL_SPEC_EXAMPLE_PATH = REFERENCES_DIR / "minimal_survey_spec.example.json"

# Host workspace output basenames (Java persistence contract)
OUTPUT_JSON_NAME = "question_schema_generate.json"
OUTPUT_HTML_NAME = "survey-unified-generate.html"
OUTPUT_CSS_NAME = "survey-ui.css"
OUTPUT_JS_NAME = "survey-ui.js"
OUTPUT_HEADER_IMAGE = "header_image.txt"


def resolve_work_dir(explicit_dir: str | Path | None = None) -> Path:
    """Resolve the host survey draft workspace directory."""
    if explicit_dir is not None:
        return Path(explicit_dir)
    return Path.cwd()
