"""统一 node --check 封装（survey-create 脚本 utils 自包含）。

与上游 survey_validation/js_syntax_check 逻辑保持一致；修改时请同步。
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

# node --check stderr 噪声清理（与 survey_validation/js_syntax_check 同源）
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_STACK_FRAME_RE = re.compile(r"^\s*at\s")
_NODE_FOOTER_RE = re.compile(r"^Node\.js\s+v")
_TMP_PATH_RE = re.compile(r"^\S*\.js:\d+\s*$")

NODE_SKIP_MESSAGE = (
    "[SKIP] node 未安装，已跳过 JS 语法 node --check。"
    "请自行复核 JS 语法（括号配对、注释边界完整）；"
    "有 node 时优先: node --check <文件路径>"
)


def clean_node_error(stderr: str) -> str:
    if not stderr:
        return stderr
    text = _ANSI_RE.sub("", stderr)
    kept: List[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if _STACK_FRAME_RE.match(line):
            continue
        if _NODE_FOOTER_RE.match(line):
            continue
        if _TMP_PATH_RE.match(line):
            continue
        kept.append(line)
    cleaned = "\n".join(kept).strip()
    return cleaned or text.strip()


def clean_escaped_string(s: str) -> str:
    if not s:
        return s
    bs = chr(92)
    result = s
    result = result.replace(bs + bs, bs)
    result = result.replace(bs + "n", chr(10))
    result = result.replace(bs + "r", chr(13))
    result = result.replace(bs + "t", chr(9))
    result = result.replace(bs + '"', '"')
    return result


def extract_script_bodies(html: str) -> List[str]:
    if not html:
        return []
    pattern = re.compile(
        "<script" + chr(92) + "b[^>]*>(.*?)</script>",
        re.DOTALL | re.IGNORECASE,
    )
    bodies: List[str] = []
    for match in pattern.finditer(html):
        text = match.group(1)
        if text and text.strip():
            bodies.append(text)
    return bodies


def node_check_scripts(scripts: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], bool]:
    errors: List[Dict[str, Any]] = []
    for item in scripts:
        fd, path = tempfile.mkstemp(suffix=".js")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(item["content"])
            result = subprocess.run(
                ["node", "--check", path],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                stderr = (result.stderr or result.stdout or "unknown error").strip()
                meta = {k: v for k, v in item.items() if k != "content"}
                meta["error"] = clean_node_error(stderr)
                errors.append(meta)
        except FileNotFoundError:
            return [], False
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
    return errors, True


def check_js_file(
    js_path: Path,
    *,
    skip_message: str | None = None,
    timeout: int = 10,
) -> Tuple[List[str], bool]:
    """对单个 .js 文件执行 node --check。

    Returns:
        (errors, node_skipped)
        node_skipped=True 表示 node 不可用，未执行检查（不计入 errors）。
    """
    if not js_path.is_file():
        return [], False

    content = js_path.read_text(encoding="utf-8")
    if not content.strip():
        return [], False

    try:
        result = subprocess.run(
            ["node", "--check", str(js_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        print(skip_message or NODE_SKIP_MESSAGE)
        return [], True
    except subprocess.TimeoutExpired:
        return [f"{js_path.name} 语法检查超时"], False

    if result.returncode != 0:
        raw = (result.stderr or result.stdout or "unknown error").strip()
        cleaned = clean_node_error(raw)
        first = cleaned.splitlines()[0] if cleaned else "未知语法错误"
        return [f"{js_path.name} 语法错误: {first}"], False

    return [], False


def check_html_script_bodies(
    html: str,
    *,
    label: str,
) -> Tuple[List[str], bool]:
    """抽取 HTML 内 <script> 体并逐段 node --check。

    Returns:
        (errors, node_skipped)
    """
    cleaned = clean_escaped_string(html or "")
    bodies = extract_script_bodies(cleaned)
    if not bodies:
        return [], False

    items = [
        {"script_index": i + 1, "content": body, "label": label}
        for i, body in enumerate(bodies)
        if body.strip()
    ]
    node_errors, sandbox_ok = node_check_scripts(items)
    if not sandbox_ok:
        print(NODE_SKIP_MESSAGE)
        return [], True

    errors: List[str] = []
    for item in node_errors:
        script_index = item.get("script_index", 1)
        raw_err = (item.get("error") or "unknown error").strip()
        errors.append(f"{label}: JS 语法错误 (script {script_index}): {raw_err}")
    return errors, False
