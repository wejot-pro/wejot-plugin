"""survey-create 脚本共享工具。"""

from .assets import ASSETS_DIR, asset_inner_js, read_asset
from .config_helpers import resolve_exam_intro, resolve_header, resolve_survey_title
from .free_css import BASE_FREE_CSS, BASE_FREE_CSS_MARKER, base_free_css_prefix, read_base_free_css
from .html_questions import ensure_default_submit_button, parse_questions, submit_button_for_locale
from .js_css_inject import (
    JS_REGION_BEGIN,
    append_css_marker,
    append_js_asset,
    inject_js_to_survey_ui,
    replace_fenced_block,
)
from .chart_html_syntax import (
    question_context_label,
    validate_chart_html_fragment,
    validate_schema_generic_chart_html,
    validate_spec_questions_chart_html,
)
from .node_js_check import NODE_SKIP_MESSAGE, check_html_script_bodies, check_js_file
from .scoring import (
    DEFAULT_AUTO_EXCLUDE_TYPES,
    NUM_TO_TYPE_NAME,
    TYPE_NAME_TO_NUM,
    check_unscorable_warnings,
    get_scoring_mapping,
    resolve_scorable_codes,
    scoring_by_uuid,
)

__all__ = [
    "ASSETS_DIR",
    "BASE_FREE_CSS",
    "BASE_FREE_CSS_MARKER",
    "DEFAULT_AUTO_EXCLUDE_TYPES",
    "JS_REGION_BEGIN",
    "NODE_SKIP_MESSAGE",
    "NUM_TO_TYPE_NAME",
    "TYPE_NAME_TO_NUM",
    "check_html_script_bodies",
    "check_js_file",
    "question_context_label",
    "validate_chart_html_fragment",
    "validate_schema_generic_chart_html",
    "validate_spec_questions_chart_html",
    "append_css_marker",
    "append_js_asset",
    "asset_inner_js",
    "base_free_css_prefix",
    "check_unscorable_warnings",
    "ensure_default_submit_button",
    "get_scoring_mapping",
    "inject_js_to_survey_ui",
    "parse_questions",
    "read_asset",
    "read_base_free_css",
    "replace_fenced_block",
    "resolve_exam_intro",
    "resolve_header",
    "resolve_survey_title",
    "resolve_scorable_codes",
    "scoring_by_uuid",
    "submit_button_for_locale",
]
