#!/usr/bin/env python3
"""校验问卷 JSON 与 HTML 一致性（含 GENERIC）。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

from utils.checkbox_choices import normalize_checkbox_choices, validate_checkbox_option_labels
from utils.chart_html_syntax import validate_schema_generic_chart_html
from utils.matrix_scale_options import validate_matrix_scale_options
from utils.node_js_check import check_js_file
from utils.radio_choices import validate_radio_option_labels
from utils.scale_options import validate_scale_option_points

from utils.skill_paths import MINIMAL_SPEC_TEMPLATE_PATH, TEMPLATE_SURVEY_UI_CSS

# Backward-compatible alias
SYSTEM_SURVEY_UI_CSS_PATH = TEMPLATE_SURVEY_UI_CSS

JSON_BUCKETS = {
    "radioQuestions": "RADIO",
    "checkboxQuestions": "CHECKBOX",
    "textQuestions": "TEXTAREA",
    "uploadQuestions": "UPLOAD",
    "scaleQuestions": "SCALE",
    "matrixScaleQuestions": "MATRIX_SCALE",
    "genericQuestions": "GENERIC",
}

JSON_TYPE_TO_HTML_TYPES = {
    "RADIO": {"8"},
    "CHECKBOX": {"9"},
    # 文本题：Agent 产物写 TEXTAREA，手动编辑 bridge 回写 INPUT，HTML 均为 data-question-type=1
    "TEXTAREA": {"1"},
    "INPUT": {"1"},
    "UPLOAD": {"15"},
    "SCALE": {"10"},
    "MATRIX_SCALE": {"28"},
    "GENERIC": {"39"},
}

HTML_TYPE_TO_JSON_TYPE = {
    "8": "RADIO",
    "9": "CHECKBOX",
    "1": "TEXTAREA",
    "15": "UPLOAD",
    "10": "SCALE",
    "28": "MATRIX_SCALE",
    "39": "GENERIC",
}

# 题目根节点 class 须同时包含以下 token（顺序不限，允许额外类名如 active）
_REQUIRED_QUESTION_ITEM_CLASSES = frozenset({"m2", "question-item", "answer-question-item"})


def _print(name: str, ok: bool, detail: str) -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def _question_item_class_ok(class_attr: str) -> bool:
    if not class_attr or not class_attr.strip():
        return False
    return _REQUIRED_QUESTION_ITEM_CLASSES.issubset(class_attr.split())


def _attrs_from_div_opening(opening_inner: str) -> dict[str, str]:
    """从 `<div ...>` 的属性串中抽取 class / data-question-uuid / data-question-type（双引号）。"""
    d: dict[str, str] = {}
    m = re.search(r'\bclass\s*=\s*"([^"]*)"', opening_inner, re.I)
    if m:
        d["class"] = m.group(1)
    m = re.search(r'\bdata-question-uuid\s*=\s*"([^"]*)"', opening_inner, re.I)
    if m:
        d["uuid"] = m.group(1)
    m = re.search(r'\bdata-question-type\s*=\s*"([^"]*)"', opening_inner, re.I)
    if m:
        d["html_type"] = m.group(1)
    return d


def _iter_question_item_opens(html: str):
    for m in re.finditer(r"<div\b([^>]+)>", html, flags=re.IGNORECASE):
        attrs = _attrs_from_div_opening(m.group(1))
        if not _question_item_class_ok(attrs.get("class", "")):
            continue
        uid, qtype = attrs.get("uuid"), attrs.get("html_type")
        if not uid or not qtype:
            continue
        yield m.end(), uid, qtype


def _read_html_questions(html: str) -> list[dict]:
    """提取所有题目根节点的 uuid 和 type，只认 data-question + data-question-uuid，不依赖 class。"""
    out = []
    pos = 0
    while True:
        # 定位下一个 data-question-uuid
        m = re.search(r'data-question-uuid="([^"]+)"', html[pos:], re.I)
        if not m:
            break
        abs_start = pos + m.start()
        uuid = m.group(1)
        # 向前找到所属 <div 开标签
        div_start = html.rfind('<div', 0, abs_start)
        if div_start == -1:
            pos = abs_start + 1
            continue
        div_end = html.find('>', abs_start)
        if div_end == -1:
            pos = abs_start + 1
            continue
        tag = html[div_start:div_end + 1]
        # 只有同时包含 data-question 的 div 才是根节点（排除 .gx 等内层容器）
        if 'data-question' not in tag.lower():
            pos = abs_start + 1
            continue
        type_m = re.search(r'data-question-type="([^"]+)"', tag, re.I)
        if type_m:
            out.append({"uuid": uuid, "html_type": type_m.group(1)})
        pos = div_end + 1
    return out


def _read_json_questions(data: dict) -> list[dict]:
    out = []
    for bucket, jtype in JSON_BUCKETS.items():
        for q in data.get(bucket, []):
            out.append({"uuid": str(q.get("uuid", "")), "json_type": str(q.get("type", jtype)), "bucket_type": jtype})
    return out


def _get_json_question_by_uuid(data: dict, uuid: str) -> dict | None:
    """按 uuid 从 schema 中查找题目原数据。"""
    for bucket in JSON_BUCKETS:
        for q in data.get(bucket, []):
            if str(q.get("uuid", "")) == uuid:
                return q
    return None


def _get_option_text_content(region: str, open_tag_end: int, tag_name: str) -> str:
    """从开标签结束位置开始，提取到对应闭标签之前的纯文本（处理简单嵌套）。"""
    pos = open_tag_end + 1
    depth = 1
    text_parts = []
    while pos < len(region):
        next_tag = re.search(r'<[^>]+>', region[pos:])
        if not next_tag:
            break
        text = region[pos:pos + next_tag.start()]
        text_parts.append(text)
        full_tag = next_tag.group(0)
        if full_tag.startswith(f'</{tag_name}>'):
            depth -= 1
            if depth == 0:
                break
        elif re.match(rf'<{tag_name}\\b', full_tag):
            depth += 1
        pos += next_tag.end()
    return re.sub(r'\s+', ' ', "".join(text_parts)).strip()


def _collect_question_roots(html: str) -> list[dict[str, int | str]]:
    """按 DOM 顺序收集题目根节点（须同时含 data-question 与 data-question-uuid）。"""
    roots: list[dict[str, int | str]] = []
    pos = 0
    while True:
        m = re.search(r'data-question-uuid="([^"]+)"', html[pos:], re.I)
        if not m:
            break
        abs_start = pos + m.start()
        uuid = m.group(1)
        div_start = html.rfind('<div', 0, abs_start)
        if div_start == -1:
            pos = abs_start + 1
            continue
        div_end = html.find('>', abs_start)
        if div_end == -1:
            pos = abs_start + 1
            continue
        tag = html[div_start:div_end + 1]
        if 'data-question' not in tag.lower():
            pos = abs_start + 1
            continue
        type_m = re.search(r'data-question-type="([^"]+)"', tag, re.I)
        if not type_m:
            pos = div_end + 1
            continue
        roots.append(
            {
                "div_start": div_start,
                "open_tag_end": div_end,
                "uuid": uuid,
                "html_type": type_m.group(1),
            }
        )
        pos = div_end + 1
    return roots


def _closing_div_end(html: str, open_tag_end: int) -> int:
    """题目根 div 闭合后 </div> 的结束位置（含）。"""
    depth = 1
    pos = open_tag_end + 1
    while pos < len(html):
        comment_start = html.find('<!--', pos)
        if comment_start != -1:
            comment_end = html.find('-->', comment_start)
            if comment_end != -1 and comment_start < min(
                html.find('<div', pos) if html.find('<div', pos) != -1 else len(html),
                html.find('</div>', pos) if html.find('</div>', pos) != -1 else len(html),
            ):
                pos = comment_end + 3
                continue

        next_open = html.find('<div', pos)
        next_close = html.find('</div>', pos)

        if next_close == -1:
            return len(html)

        if next_open != -1 and next_open < next_close:
            depth += 1
            pos = next_open + 4
        else:
            depth -= 1
            if depth == 0:
                return next_close + 6
            pos = next_close + 6

    return len(html)


def _extract_question_region(html: str, uuid: str, qtype: str) -> str | None:
    """从 HTML 中提取单个题目的区域（含根标签本身）。

    边界以 DOM 题目根顺序为准：当前根起点至下一题根起点（或最后一题至 INSERT_POINT / 根 div 闭合）。
    不依赖 QUESTION_REGION 注释，避免编辑器残留 orphan 注释导致跨题误匹配。
    """
    roots = _collect_question_roots(html)
    for i, root in enumerate(roots):
        if root["uuid"] != uuid:
            continue
        start = int(root["div_start"])
        if i + 1 < len(roots):
            end = int(roots[i + 1]["div_start"])
        else:
            open_tag_end = int(root["open_tag_end"])
            insert = html.find('<!-- QUESTION_INSERT_POINT', open_tag_end)
            if insert == -1:
                insert = html.lower().find('<!-- question_insert_point', open_tag_end)
            end = insert if insert != -1 else _closing_div_end(html, open_tag_end)
        return html[start:end]
    return None


def _validate_generic(json_data: dict, html: str, html_qs: list[dict]) -> list[str]:
    errors: list[str] = []
    generic_json = json_data.get("genericQuestions", [])
    generic_uuids = [q.get("uuid", "") for q in generic_json if q.get("uuid")]
    html_generic_uuids = [q["uuid"] for q in html_qs if q["html_type"] == "39"]

    for i, q in enumerate(generic_json, start=1):
        if not isinstance(q.get("answerKeys"), list) or not q.get("answerKeys"):
            errors.append(f"genericQuestions[{i}] 缺少非空 answerKeys")

    for uid in set(generic_uuids) | set(html_generic_uuids):
        region = _extract_question_region(html, uid, "39")
        if region is None:
            errors.append(f"GENERIC question-item 缺失: {uid}")
            continue
        if f'data-survey-role="generic-container"' not in region:
            errors.append(f"GENERIC 缺少 data-survey-role=\"generic-container\": {uid}")
        if f'data-question-uuid="{uid}"' not in region:
            errors.append(f"GENERIC 内层 data-question-uuid 不一致: {uid}")
        km = re.search(
            r'<script[^>]*data-answer-keys="([^"]+)"',
            region,
            flags=re.S,
        )
        if not km:
            errors.append(f"GENERIC data-answer-keys 缺失: {uid}")
            continue
        html_keys = [x.strip() for x in km.group(1).split(",") if x.strip()]
        q_json = next((x for x in generic_json if x.get("uuid") == uid), None)
        if q_json is not None and html_keys != q_json.get("answerKeys", []):
            errors.append(f"GENERIC answerKeys 不一致: {uid}")

    if len(generic_uuids) != len(html_generic_uuids):
        errors.append(f"GENERIC 数量不一致: json={len(generic_uuids)} html={len(html_generic_uuids)}")
    return errors


_GENERIC_IDENTITY_ATTRIBUTES = frozenset({"class", "id", "name", "role", "for"})
_GENERIC_DEFAULT_HTML = "<!-- 自定义题html结构 -->"


class _GenericHtmlAttributeParser(HTMLParser):
    """收集 GENERIC HTML 的实际属性值，HTMLParser 对容错 HTML 保持宽松。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.attributes: list[tuple[str, str, str | None]] = []

    def _collect(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            self.attributes.append((tag, name.lower(), value))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._collect(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._collect(tag, attrs)


def _parse_generic_html_attributes(html: str) -> _GenericHtmlAttributeParser:
    parser = _GenericHtmlAttributeParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # HTMLParser is intentionally only a best-effort signal here. The
        # validator must not reject custom markup solely because it is unusual.
        pass
    return parser


def _is_double_escaped_quoted_value(value: str | None) -> bool:
    """识别 HTML 中不生效的 `\\"value\\"` / `\\'value\\'` 属性值。"""
    return bool(value and re.fullmatch(r'''\\(["']).*\\\1''', value, flags=re.S))


def _extract_simple_query_selectors(script: str) -> list[str]:
    """只提取静态、无歧义的简单 querySelector 选择器。"""
    selectors: list[str] = []
    pattern = re.compile(
        r'''querySelector(?:All)?\(\s*(["'])(#[A-Za-z_][\w:-]*|\.[A-Za-z_][\w-]*|\[data-role\s*=\s*["'][^"']+["']\])\1'''
    )
    for match in pattern.finditer(script):
        selector = match.group(2)
        if selector not in selectors:
            selectors.append(selector)
    return selectors


def _simple_selector_present(html: str, selector: str) -> bool:
    parser = _parse_generic_html_attributes(html)
    if selector.startswith("#"):
        return any(
            name == "id" and value == selector[1:]
            for _, name, value in parser.attributes
        )
    if selector.startswith("."):
        wanted = selector[1:]
        return any(
            name == "class" and wanted in str(value or "").split()
            for _, name, value in parser.attributes
        )
    role_match = re.fullmatch(r'''\[data-role\s*=\s*["']([^"']+)["']\]''', selector)
    if role_match:
        wanted = role_match.group(1)
        return any(
            name == "data-role" and value == wanted
            for _, name, value in parser.attributes
        )
    return True


def _validate_generic_html_quality(json_data: dict, html: str) -> tuple[list[str], list[str]]:
    """检查 GENERIC 自定义 HTML 的明显错误，并对动态组件给出非阻断提示。

    这里只拦截高置信度问题：空/占位 HTML，以及 selector 身份属性中的双重转义。
    选择器静态找不到目标只作为 warning，因为目标可能由 genericScript 动态创建。
    """
    errors: list[str] = []
    warnings: list[str] = []
    for index, question in enumerate(json_data.get("genericQuestions", []), start=1):
        uid = str(question.get("uuid") or f"genericQuestions[{index}]")
        generic_html = question.get("genericHtml")
        if not isinstance(generic_html, str) or not generic_html.strip():
            errors.append(f"{uid} genericHtml 为空")
            continue
        if generic_html.strip() == _GENERIC_DEFAULT_HTML:
            errors.append(f"{uid} genericHtml 仍是默认占位内容")
            continue

        parser = _parse_generic_html_attributes(generic_html)
        for tag, name, value in parser.attributes:
            is_identity_attr = (
                name in _GENERIC_IDENTITY_ATTRIBUTES
                or name.startswith("data-")
                or name.startswith("aria-")
            )
            if is_identity_attr and _is_double_escaped_quoted_value(value):
                errors.append(
                    f"{uid} genericHtml 属性 {name} 双重转义（<{tag}> 的值 {value!r} 不会按预期匹配 DOM 选择器）"
                )

        script = question.get("genericScript")
        if not isinstance(script, str):
            continue
        region = _extract_question_region(html, uid, "39") or generic_html
        for selector in _extract_simple_query_selectors(script):
            if not _simple_selector_present(region, selector):
                warnings.append(
                    f"{uid} genericScript 静态选择器 {selector!r} 在当前 HTML 中未找到目标；"
                    "若由脚本动态创建元素可忽略"
                )
    return errors, warnings


def _validate_options_consistency(json_data: dict, html: str, html_qs: list[dict]) -> list[str]:
    """校验 JSON schema 与 HTML 之间 RADIO/CHECKBOX 的选项数量及"其它"选项一致性。"""
    errors: list[str] = []
    for q in html_qs:
        uid = q["uuid"]
        t = q["html_type"]
        if t not in ("8", "9"):
            continue
        region = _extract_question_region(html, uid, t)
        if region is None:
            continue

        json_q = _get_json_question_by_uuid(json_data, uid)
        if json_q is None:
            continue

        # HTML 中的选项数量（排除 matrix scale 选项）
        html_opts_raw = re.findall(r'<[^>]*\bdata-option\b[^>]*>', region)
        html_opts = 0
        for opt_tag in html_opts_raw:
            if 'data-scale-value' not in opt_tag:
                html_opts += 1

        # JSON 中的选项数量
        json_opts = json_q.get("options", []) or []
        json_opt_count = len(json_opts)

        # HTML 中是否有 data-option-other
        has_html_other = 'data-option-other' in region

        # JSON 中是否明确开启"其它"：新契约必须使用 otherEnabled=1
        last_json_label = str(json_opts[-1].get("label", "")) if json_opts else ""
        has_json_other = int(json_q.get("otherEnabled", 0) or 0) == 1

        if int(json_q.get("otherEnabled", 0) or 0) == 1 and last_json_label == "其它":
            errors.append(
                f"{uid} (type={t}) 已设置 otherEnabled=1，JSON options 中不应再包含'其它'普通选项"
            )
            continue
        if has_html_other and last_json_label == "其它" and not has_json_other:
            errors.append(
                f"{uid} (type={t}) HTML 中有 data-option-other，JSON 必须设置 otherEnabled=1，不能只在 options 中添加'其它'"
            )
            continue

        # 如果 JSON 有"其它"但 HTML 没有 data-option-other，或者反过来
        if has_json_other != has_html_other:
            if has_json_other:
                errors.append(
                    f"{uid} (type={t}) JSON 中有'其它'选项，但 HTML 缺少 data-option-other"
                )
            else:
                errors.append(
                    f"{uid} (type={t}) HTML 中有 data-option-other，但 JSON 缺少 otherEnabled=1"
                )
            continue

        # 比较选项总数（otherEnabled=1 时，HTML 额外包含一个虚拟"其它"选项）
        expected_json_count = json_opt_count + (1 if has_json_other else 0)
        if expected_json_count != html_opts:
            errors.append(
                f"{uid} (type={t}) 选项数量不一致: json={expected_json_count}, html={html_opts}"
            )

        # 校验 CHECKBOX 的 minChoices / maxChoices 一致性
        if t == "9":
            json_min, json_max = normalize_checkbox_choices(
                json_q.get("minChoices"),
                json_q.get("maxChoices"),
                option_count=expected_json_count,
            )
            html_min_match = re.search(r'data-min-choices="(\d+)"', region)
            html_max_match = re.search(r'data-max-choices="(\d+)"', region)
            html_min = int(html_min_match.group(1)) if html_min_match else None
            html_max = int(html_max_match.group(1)) if html_max_match else None
            if html_min is not None and html_min != json_min:
                errors.append(
                    f"{uid} (CHECKBOX) data-min-choices 不一致: json={json_min}, html={html_min}"
                )
            if html_max is not None and html_max != json_max:
                errors.append(
                    f"{uid} (CHECKBOX) data-max-choices 不一致: json={json_max}, html={html_max}"
                )

    return errors


def _validate_option_content_consistency(json_data: dict, html: str, html_qs: list[dict]) -> list[str]:
    """校验 RADIO/CHECKBOX/SCALE/MATRIX 选项文案或分值与 JSON schema 一致。"""
    errors: list[str] = []
    for q in html_qs:
        uid = q["uuid"]
        t = q["html_type"]
        if t not in ("8", "9", "10", "28"):
            continue
        region = _extract_question_region(html, uid, t)
        if region is None:
            continue
        json_q = _get_json_question_by_uuid(json_data, uid)
        if json_q is None:
            continue
        if t == "8":
            errors.extend(validate_radio_option_labels(json_q, region, uid))
        elif t == "9":
            errors.extend(validate_checkbox_option_labels(json_q, region, uid))
        elif t == "10":
            errors.extend(validate_scale_option_points(json_q, region, uid))
        elif t == "28":
            errors.extend(validate_matrix_scale_options(json_q, region, uid))
    return errors


def _validate_html_data_attrs(html: str, html_qs: list[dict]) -> list[str]:
    """校验 HTML 中各题型的 data-* 属性完整性（供 collectSurveyData 读取）。"""
    errors: list[str] = []
    for q in html_qs:
        uid = q["uuid"]
        t = q["html_type"]
        region = _extract_question_region(html, uid, t)
        if region is None:
            continue

        if t in ("8", "9"):
            # 校验每个选项（带 data-option 的元素）含有非空纯文本内容
            # 排除量表/矩阵分值选项（带 data-scale-value 的 data-option 不需要文本标签）
            opt_blocks = re.findall(r'<(\w+)\b([^>]*\bdata-option\b[^>]*)>(.*?)</\1>', region, re.S)
            total = 0
            missing = 0
            for _tag, attrs, inner in opt_blocks:
                if 'data-scale-value' in attrs:
                    continue
                total += 1
                # 去掉内部标签后判断是否仍有可读文本（input 等无文本节点不计）
                if not re.sub(r'<[^>]*>', '', inner).strip():
                    missing += 1
            if missing > 0:
                errors.append(f"{uid} (type={t}) 存在缺少可读文本内容的选项 ({missing}/{total} 缺失)")

        if t == "9":
            if "data-min-choices=" not in region:
                errors.append(f"{uid} (CHECKBOX) 缺少 data-min-choices")
            if "data-max-choices=" not in region:
                errors.append(f"{uid} (CHECKBOX) 缺少 data-max-choices")

        if t == "10":
            scs = len(re.findall(r'<div[^>]*\bdata-option\b[^>]*\bdata-scale-value="[^"]*"[^>]*>', region))
            vals = len(re.findall(r'\bdata-scale-value="[^"]*"', region))
            if vals < scs:
                errors.append(f"{uid} (SCALE) 存在缺少 data-scale-value 的选项 ({vals}/{scs})")

        if t in ("14", "15"):
            if "data-max-file-count=" not in region:
                errors.append(f"{uid} (UPLOAD) 缺少 data-max-file-count")
            if "data-max-file-size=" not in region:
                errors.append(f"{uid} (UPLOAD) 缺少 data-max-file-size")

        if t == "28":
            rows = len(re.findall(r'\bdata-survey-role="matrix-row"', region))
            # 要求行标题非空：[^"]*\S[^"]* 至少含一个非空白字符，拦截 data-matrix-row-label=""
            # 或纯空白——空行标题会让后端 matrix_scale_row.title 插入 NULL，导致整卷入库 500。
            row_labels = len(re.findall(r'\bdata-matrix-row-label="[^"]*\S[^"]*"', region))
            if row_labels < rows:
                errors.append(f"{uid} (MATRIX) 存在缺少/为空的 data-matrix-row-label 行 ({row_labels}/{rows})")
            scs = len(re.findall(r'<div[^>]*\bdata-option\b[^>]*\bdata-scale-value="[^"]*"[^>]*>', region))
            vals = len(re.findall(r'\bdata-scale-value="[^"]*"', region))
            if vals < scs:
                errors.append(f"{uid} (MATRIX) 存在缺少 data-scale-value 的列 ({vals}/{scs})")

    return errors


def _validate_dynamic_matrix_schema(json_data: dict) -> list[str]:
    """Validate the persisted boundary for bounded dynamic matrix rows."""
    errors: list[str] = []
    for bucket in JSON_BUCKETS:
        if bucket == "matrixScaleQuestions":
            continue
        for index, question in enumerate(json_data.get(bucket, []) or [], start=1):
            if not isinstance(question, dict) or "dynamicRows" not in question:
                continue
            uid = str(question.get("uuid") or f"{bucket}[{index}]")
            errors.append(f"{uid} dynamicRows 只允许用于 MATRIX_SCALE")

    for index, question in enumerate(
        json_data.get("matrixScaleQuestions", []) or [], start=1
    ):
        if not isinstance(question, dict):
            continue
        uid = str(question.get("uuid") or f"matrixScaleQuestions[{index}]")
        dynamic_rows = question.get("dynamicRows", False)
        if not isinstance(dynamic_rows, bool):
            errors.append(f"{uid} dynamicRows 必须为 boolean")
            continue
        rows = question.get("rows")
        if not isinstance(rows, list) or not rows:
            errors.append(f"{uid} MATRIX_SCALE 必须声明非空 rows catalog")
            continue
        titles = [
            str((row or {}).get("rowTitle", (row or {}).get("title", ""))).strip()
            for row in rows
            if isinstance(row, dict)
        ]
        if len(titles) != len(rows) or any(not title for title in titles):
            errors.append(f"{uid} rows catalog 存在空或非法 rowTitle")
        elif len(set(titles)) != len(titles):
            errors.append(f"{uid} rows catalog 的 rowTitle 必须唯一")
    return errors


def _validate_survey_ui_js(js_path: Path) -> list[str]:
    """校验 survey-ui.js 语法与逻辑规范。若文件不存在（完全自定义问卷可不使用基座），跳过校验。"""
    errors: list[str] = []
    if not js_path.exists():
        print("[INFO] survey-ui.js 不存在，跳过 JS 基座校验（完全自定义问卷可不使用基座）")
        return errors

    content = js_path.read_text(encoding="utf-8")
    if not content.strip():
        print("[INFO] survey-ui.js 为空，跳过 JS 基座校验")
        return errors

    # 1. 语法检查（调用 node --check）
    syntax_errors, _node_skipped = check_js_file(
        js_path,
        skip_message=(
            "[SKIP] node 未安装，已跳过 survey-ui.js 的 node --check。"
            "请自行复核 JS 语法（注释边界完整、无裸露中文/残缺 /* */、括号与 IIFE 配对）；"
            f"有 node 时优先: node --check {js_path}"
        ),
    )
    errors.extend(syntax_errors)

    # 2. 检测基座模式 or 自由模式
    begin_matches = re.findall(r"// ==================== 业务逻辑扩展区 BEGIN ====================", content)
    end_matches = re.findall(r"// ==================== 业务逻辑扩展区 END ====================", content)
    if len(begin_matches) > 1:
        errors.append(f"survey-ui.js 含 {len(begin_matches)} 个业务逻辑扩展区 BEGIN；必须保留唯一可编辑区")
    if len(end_matches) > 1:
        errors.append(f"survey-ui.js 含 {len(end_matches)} 个业务逻辑扩展区 END；必须保留唯一可编辑区")
    begin_m = re.search(r"// ==================== 业务逻辑扩展区 BEGIN ====================", content)
    end_m = re.search(r"// ==================== 业务逻辑扩展区 END ====================", content)
    has_base_markers = bool(begin_m and end_m)
    has_data_bridge_ref = bool(re.search(r"SurveyDataBridge|saveAnswerLocal|surveyAnswerChanged", content))

    if has_base_markers:
        has_infra_begin = "SURVEY_UI_INFRA_BEGIN" in content
        has_infra_end = "SURVEY_UI_INFRA_END" in content
        has_runtime_export = bool(re.search(r"\bwindow\.SurveyRuntime\s*=\s*\{", content))
        if not (has_infra_begin and has_infra_end and has_runtime_export):
            errors.append(
                "survey-ui.js 含标准业务逻辑扩展区，但 Runtime 基座不完整；"
                "请从系统模板恢复 SURVEY_UI_INFRA_BEGIN/END 及 window.SurveyRuntime 导出，"
                "业务代码仅保留在 BEGIN/END 扩展区内"
            )

        # 标准基座模式：检查扩展区规范
        extension_code = content[begin_m.end():end_m.start()]
        # 去掉注释和空白，检查是否为空
        clean = re.sub(r"//.*", "", extension_code)
        clean = re.sub(r"/\*[\s\S]*?\*/", "", clean)
        clean = re.sub(r"\s+", "", clean)
        if "registerUserLogic" not in clean:
            print("[INFO] 业务逻辑扩展区为空：未检测到 registerUserLogic。若问卷确实不需要显隐/跳转/分支逻辑，可忽略。")

        # 禁止模式检测（只在业务逻辑扩展区内检测，避免基座代码误报）
        forbidden_patterns = [
            (r"\.questionIndex", "禁止使用 e.detail.questionIndex，事件 detail 只提供 questionUuid/questionType/value/rawValue"),
            (r"getAnswerByIndex\s*\(", "禁止使用 getAnswerByIndex，请用 resolveUuidByIndex + getAnswer"),
            (r"document\.currentScript", "禁止在 survey-ui.js 中使用 document.currentScript"),
        ]
        for pattern, msg in forbidden_patterns:
            if re.search(pattern, extension_code):
                errors.append(msg)

        # 检测 DOMContentLoaded 监听（只在业务逻辑扩展区内检测）
        if re.search(r"addEventListener\s*\(\s*['\"]DOMContentLoaded['\"]", extension_code):
            errors.append("禁止在 survey-ui.js 中监听 DOMContentLoaded，基座会自动执行业务逻辑")

    else:
        # 自由模式：无基座标记，豁免 BEGIN/END 和 DOMContentLoaded 检查
        # 但需确认 LLM 至少意识到数据层存在（引用 SurveyDataBridge / saveAnswerLocal / surveyAnswerChanged）
        if not has_data_bridge_ref:
            errors.append("survey-ui.js 未检测到基座标记，且未引用 SurveyDataBridge / saveAnswerLocal / surveyAnswerChanged。自由模式下请确保数据提交链路正常（如调用 SurveyDataBridge.submit() 或保持 bridge.js 自动绑定兼容）。")
        extension_code = content

    return errors


def _validate_generic_script(html: str) -> list[str]:
    """校验 GENERIC genericScript 中的禁止模式。"""
    errors: list[str] = []
    # 提取所有 genericScript
    for m in re.finditer(r'<script\s+data-answer-keys="[^"]*"[^>]*>(.*?)</script>', html, re.S):
        script = m.group(1)
        # 去掉外层 try-catch 包装，取实际代码
        inner = re.sub(r"^\s*try\s*\{", "", script)
        inner = re.sub(r"\}\s*catch\s*\([^)]*\)\s*\{[^}]*\}\s*$", "", inner, flags=re.S)
        if re.search(r"addEventListener\s*\(\s*['\"]surveyAnswerChanged['\"]", inner):
            errors.append("GENERIC genericScript 禁止监听 surveyAnswerChanged，问卷级显隐/分支逻辑必须写在 survey-ui.js 扩展区")
        if re.search(r"getAnswerByIndex\s*\(", inner):
            errors.append("GENERIC genericScript 禁止使用 getAnswerByIndex")
        if re.search(
            r"\bdocument\s*\.\s*querySelector(?:All)?\s*\(\s*(['\"]).*?"
            r"(?:data-question(?:-uuid)?|data-code).*?\1",
            inner,
            flags=re.S,
        ):
            errors.append(
                "GENERIC genericScript 禁止读取其它题 DOM；只能查询本题 wrapper 内部。"
                "跨题候选必须由 survey-ui.js 通过 getSelectedQuestionItems -> "
                "setQuestionItems(..., { slot: 'genericItems' }) 注入"
            )
        listens_for_dynamic_items = re.search(
            r"addEventListener\s*\(\s*['\"]survey:question-items['\"]",
            inner,
        )
        reads_candidate_items = re.search(r"\b(?:detail|\w+\.detail)\.items\b", inner)
        uses_typed_item_key = re.search(r"\.itemKey\b|\bitemKey\s*:", inner)
        maps_value_to_item_key = re.search(
            r"\bitemKey\s*:\s*[A-Za-z_$][\w$]*\.value\b", inner
        )
        if (
            listens_for_dynamic_items
            and reads_candidate_items
            and uses_typed_item_key
            and not maps_value_to_item_key
        ):
            errors.append(
                "GENERIC 动态题项必须把候选 item.value 映射为 typed answer 的 "
                "itemKey；detail.items 不能直接当作答案项使用"
            )
    return errors


def _validate_dom_page_placement(html: str, html_qs: list[dict]) -> list[str]:
    """校验 DOM 中题目实际所在页面段与 data-page 属性是否一致。

    运行时 survey-ui.js 通过 .pb[data-page-break] 切分页面，而非 data-page 属性。
    若题目 data-page 与 DOM 结构中的页面段不符，会导致分页错乱。
    """
    errors: list[str] = []

    # 提取 QUESTION_LIST_START ~ QUESTION_INSERT_POINT 区间的题目区域
    region_match = re.search(
        r'(<!-- QUESTION_LIST_START:.*?-->)(.*?)(<!-- QUESTION_INSERT_POINT:.*?-->)',
        html,
        flags=re.S,
    )
    if not region_match:
        return errors
    region = region_match.group(2)

    current_dom_page: int | None = None
    seen_pages: list[int] = []

    # 逐 token 遍历：page-break div 和 question-item div
    token_pattern = re.compile(
        r'<div\b[^>]*?(?:data-page-break="(\d+)"|data-question-uuid="([^"]+)"[^>]*?data-page="(\d+)")[^>]*>',
        flags=re.I,
    )

    for m in token_pattern.finditer(region):
        page_break_val = m.group(1)
        q_uuid = m.group(2)
        q_page_val = m.group(3)

        if page_break_val is not None:
            new_page = int(page_break_val)
            if current_dom_page is not None and new_page <= current_dom_page:
                errors.append(
                    f"页面分隔符顺序异常: data-page-break=\"{new_page}\" 出现在页面 {current_dom_page} 之后，"
                    "页面编号必须严格递增"
                )
            current_dom_page = new_page
            seen_pages.append(new_page)
        elif q_uuid is not None:
            q_page = int(q_page_val)
            if current_dom_page is None:
                errors.append(
                    f"{q_uuid} 出现在任何页面分隔符之前（data-page-break），"
                    "每个题目必须位于某个页面分隔符之后"
                )
            elif q_page != current_dom_page:
                errors.append(
                    f"{q_uuid} 的 data-page=\"{q_page}\" 与 DOM 实际所在页面 {current_dom_page} 不一致，"
                    "请调整 questions 数组顺序使同一页的题目连续排列"
                )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default=None, help="问卷产物目录，默认从当前目录查找")
    parser.add_argument(
        "--keep-spec",
        action="store_true",
        help="校验通过后保留工作目录下的 *spec.json 草稿（调试用）",
    )
    args = parser.parse_args()

    if args.dir:
        work_dir = Path(args.dir)
    else:
        work_dir = Path.cwd()
        if not (work_dir / "question_schema_generate.json").exists():
            print(
                "[WARN] 未找到 question_schema_generate.json；请用 --dir 指定问卷工作区",
                file=sys.stderr,
            )

    json_path = work_dir / "question_schema_generate.json"
    html_path = work_dir / "survey-unified-generate.html"

    json_data = json.loads(json_path.read_text(encoding="utf-8"))
    html = html_path.read_text(encoding="utf-8")
    json_qs = _read_json_questions(json_data)
    html_qs = _read_html_questions(html)

    failed = False

    ok_total = len(json_qs) == len(html_qs)
    _print("题目总数", ok_total, f"json={len(json_qs)}, html={len(html_qs)}")
    failed |= not ok_total
    if len(json_qs) == 0 and len(html_qs) == 0:
        print("[WARN] 题目数量为 0：当前产物仅包含问卷标题/描述，无题目内容。")
        print(f"[WARN] 若这并非预期，请按示例 spec 修正后重试：{MINIMAL_SPEC_TEMPLATE_PATH}")

    json_uuids = [q["uuid"] for q in json_qs if q["uuid"]]
    html_uuids = [q["uuid"] for q in html_qs if q["uuid"]]
    jdup = [u for u, c in Counter(json_uuids).items() if c > 1]
    hdup = [u for u, c in Counter(html_uuids).items() if c > 1]
    only_j = sorted(set(json_uuids) - set(html_uuids))
    only_h = sorted(set(html_uuids) - set(json_uuids))
    ok_uuid = not jdup and not hdup and not only_j and not only_h
    _print("UUID 数量与集合", ok_uuid, f"json_dup={len(jdup)}, html_dup={len(hdup)}, only_json={len(only_j)}, only_html={len(only_h)}")
    failed |= not ok_uuid

    json_bucket = Counter([q["bucket_type"] for q in json_qs])
    html_bucket = Counter([HTML_TYPE_TO_JSON_TYPE.get(q["html_type"], "UNKNOWN") for q in html_qs])
    mismatch = [t for t in set(json_bucket) | set(html_bucket) if json_bucket.get(t, 0) != html_bucket.get(t, 0)]
    ok_bucket = len(mismatch) == 0
    _print("按题型分桶数量", ok_bucket, f"json={dict(json_bucket)}, html={dict(html_bucket)}")
    failed |= not ok_bucket

    json_by_uuid = {q["uuid"]: q["json_type"] for q in json_qs if q["uuid"]}
    html_by_uuid = {q["uuid"]: q["html_type"] for q in html_qs if q["uuid"]}
    mapping_errors = []
    for uid in sorted(set(json_by_uuid) & set(html_by_uuid)):
        expected = JSON_TYPE_TO_HTML_TYPES.get(json_by_uuid[uid], set())
        if html_by_uuid[uid] not in expected:
            mapping_errors.append(uid)
    ok_map = len(mapping_errors) == 0
    _print("type 映射一致性", ok_map, f"errors={len(mapping_errors)}")
    failed |= not ok_map

    generic_errors = _validate_generic(json_data, html, html_qs)
    ok_generic = len(generic_errors) == 0
    _print("GENERIC 结构与字段", ok_generic, f"errors={len(generic_errors)}")
    if generic_errors:
        for e in generic_errors[:10]:
            print(f"  - {e}")
    failed |= not ok_generic

    dynamic_matrix_errors = _validate_dynamic_matrix_schema(json_data)
    ok_dynamic_matrix = len(dynamic_matrix_errors) == 0
    _print(
        "动态矩阵 schema catalog",
        ok_dynamic_matrix,
        f"errors={len(dynamic_matrix_errors)}",
    )
    if dynamic_matrix_errors:
        for error in dynamic_matrix_errors[:10]:
            print(f"  - {error}")
    failed |= not ok_dynamic_matrix

    generic_html_errors, generic_html_warnings = _validate_generic_html_quality(json_data, html)
    ok_generic_html = len(generic_html_errors) == 0
    _print(
        "GENERIC genericHtml 基础可用性",
        ok_generic_html,
        f"errors={len(generic_html_errors)}, warnings={len(generic_html_warnings)}",
    )
    if generic_html_errors:
        for e in generic_html_errors[:10]:
            print(f"  - {e}")
    if generic_html_warnings:
        for warning in generic_html_warnings[:10]:
            print(f"  [WARN] {warning}")
    failed |= not ok_generic_html

    chart_html_errors = validate_schema_generic_chart_html(json_data)
    ok_chart_html = len(chart_html_errors) == 0
    _print("GENERIC chartHtml JS 语法", ok_chart_html, f"errors={len(chart_html_errors)}")
    if chart_html_errors:
        for e in chart_html_errors[:10]:
            print(f"  - {e}")
    failed |= not ok_chart_html

    data_attr_errors = _validate_html_data_attrs(html, html_qs)
    ok_data_attrs = len(data_attr_errors) == 0
    _print("HTML data-* 属性完整性", ok_data_attrs, f"errors={len(data_attr_errors)}")
    if data_attr_errors:
        for e in data_attr_errors[:10]:
            print(f"  - {e}")
    failed |= not ok_data_attrs

    option_consistency_errors = _validate_options_consistency(json_data, html, html_qs)
    ok_options = len(option_consistency_errors) == 0
    _print("RADIO/CHECKBOX 选项数量一致性", ok_options, f"errors={len(option_consistency_errors)}")
    if option_consistency_errors:
        for e in option_consistency_errors[:10]:
            print(f"  - {e}")
    failed |= not ok_options

    option_content_errors = _validate_option_content_consistency(json_data, html, html_qs)
    ok_option_content = len(option_content_errors) == 0
    _print("HTML JSON 的选项文案一致性(必须全部修正，否则将导致答案收集失败)：", ok_option_content, f"errors={len(option_content_errors)}")
    if option_content_errors:
        for e in option_content_errors[:10]:
            print(f"  - {e}")
    failed |= not ok_option_content

    # survey-ui.css：标准模式入库依赖外链样式文件，缺失时须提示 Agent 手动从模板拷贝
    ui_css_path = work_dir / "survey-ui.css"
    ok_css = ui_css_path.is_file()
    _print("survey-ui.css 存在性", ok_css, f"path={ui_css_path}")
    if not ok_css:
        print(
            "  - survey-ui.css 不存在。请手动从模板复制到当前问卷工作目录后重试校验：\n"
            f"    cp {SYSTEM_SURVEY_UI_CSS_PATH} {ui_css_path}"
        )
    failed |= not ok_css

    # survey-ui.js 语法与规范校验（完全自定义问卷可不使用基座）
    ui_js_path = work_dir / "survey-ui.js"
    ui_errors = _validate_survey_ui_js(ui_js_path)
    ok_ui = len(ui_errors) == 0
    if ui_js_path.exists():
        _print("survey-ui.js 语法与规范", ok_ui, f"errors={len(ui_errors)}")
    else:
        print(f"[SKIP] survey-ui.js 语法与规范: 文件不存在（完全自定义问卷可不使用基座）")
    if ui_errors:
        for e in ui_errors[:10]:
            print(f"  - {e}")
    failed |= not ok_ui

    # genericScript 禁止模式校验
    generic_script_errors = _validate_generic_script(html)
    ok_generic_script = len(generic_script_errors) == 0
    _print("GENERIC genericScript 规范", ok_generic_script, f"errors={len(generic_script_errors)}")
    if generic_script_errors:
        for e in generic_script_errors[:10]:
            print(f"  - {e}")
    failed |= not ok_generic_script

    # DOM 页面放置一致性校验（data-page 与 .pb[data-page-break] 段是否匹配）
    dom_page_errors = _validate_dom_page_placement(html, html_qs)
    ok_dom_page = len(dom_page_errors) == 0
    _print("DOM 页面放置一致性", ok_dom_page, f"errors={len(dom_page_errors)}")
    if dom_page_errors:
        for e in dom_page_errors[:10]:
            print(f"  - {e}")
    failed |= not ok_dom_page

    print("\n校验结论:", "失败" if failed else "通过")
    if failed:
        return 1

    if not args.keep_spec:
        removed: list[Path] = []
        for path in sorted(work_dir.glob("*spec.json")):
            if path.is_file():
                path.unlink()
                removed.append(path.resolve())
        if removed:
            print(f"已清理 spec 草稿 ({len(removed)} 个):")
            for p in removed:
                print(f"  - {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
