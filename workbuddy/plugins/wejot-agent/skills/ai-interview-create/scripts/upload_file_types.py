"""上传题 fileTypes 白名单与归一化。

⚠️ 须与 Java UploadSurveyQuestionHandler.allowedExtensions、
以及 survey-create/scripts/generate_standard_survey.py 的 ALLOWED_FILE_EXTENSIONS
保持一致，否则上传题会入库失败。
"""

from __future__ import annotations

from typing import Any

ALLOWED_FILE_EXTENSIONS = [
    # 图片
    "jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "heic", "tiff",
    # 文档
    "pdf", "doc", "docx", "xls", "xlsx", "csv", "ppt", "pptx", "txt", "rtf", "md",
    # 压缩包
    "zip", "rar", "7z", "gz", "tar",
    # 音频
    "mp3", "wav", "m4a", "aac", "ogg", "flac",
    # 视频
    "mp4", "mov", "avi", "mkv", "webm", "wmv", "flv",
]
_ALLOWED_FILE_EXTENSIONS_SET = set(ALLOWED_FILE_EXTENSIONS)

_MIME_WILDCARD_MAP = {
    "image/*": ["jpg", "jpeg", "png", "gif", "bmp", "webp", "svg", "heic", "tiff"],
    "audio/*": ["mp3", "wav", "m4a", "aac", "ogg", "flac"],
    "video/*": ["mp4", "mov", "avi", "mkv", "webm", "wmv", "flv"],
}
_MIME_TO_EXT = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "text/plain": "txt",
    "text/csv": "csv",
    "application/zip": "zip",
    "application/x-rar-compressed": "rar",
    "application/x-7z-compressed": "7z",
}


def normalize_file_types(raw: Any) -> list[str]:
    """将 fileTypes 归一化为 Java 可入库的「小写、无点扩展名」白名单子集。

    兼容 AI 可能写出的多种格式：
    - 带点 ".pdf" / 大写 "PDF" → "pdf"
    - MIME 通配 "image/*" / "audio/*" / "video/*" → 展开为对应扩展名
    - 常见完整 MIME → 扩展名
    白名单外的项直接丢弃；全部不合法或非列表时返回 []（调用方回退默认值）。
    """
    if not isinstance(raw, list):
        return []
    result: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        token = item.strip().lower()
        if not token:
            continue
        if token in _MIME_WILDCARD_MAP:
            candidates = _MIME_WILDCARD_MAP[token]
        elif token in _MIME_TO_EXT:
            candidates = [_MIME_TO_EXT[token]]
        else:
            ext = token.lstrip(".")
            if "/" in ext:
                ext = ext.split("/", 1)[1]
            candidates = [ext]
        for ext in candidates:
            if ext in _ALLOWED_FILE_EXTENSIONS_SET and ext not in result:
                result.append(ext)
    return result
