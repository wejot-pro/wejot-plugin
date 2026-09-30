#!/usr/bin/env python3
"""Download and safely materialize a WeJot survey artifact bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath


ARTIFACT_FILES = (
    "survey-unified-generate.html",
    "survey-ui.css",
    "survey-ui.js",
    "question_schema_generate.json",
)
CHUNK_SIZE = 64 * 1024
DEFAULT_MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024


class PullError(Exception):
    """A stable, user-facing pull failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _validate_inputs(url: str, expected_sha256: str, expected_size: int, output_dir: Path) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PullError("INVALID_ARGUMENT", "bundle URL must use http or https")
    normalized_sha = expected_sha256.lower()
    if len(normalized_sha) != 64 or any(char not in "0123456789abcdef" for char in normalized_sha):
        raise PullError("INVALID_ARGUMENT", "sha256 must be 64 lowercase hexadecimal characters")
    if expected_size <= 0:
        raise PullError("INVALID_ARGUMENT", "size-bytes must be greater than zero")
    if output_dir.exists() and not output_dir.is_dir():
        raise PullError("INVALID_ARGUMENT", "output-dir exists and is not a directory")


def _download(url: str, destination: Path, expected_size: int) -> str:
    digest = hashlib.sha256()
    received = 0
    request = urllib.request.Request(url, headers={"User-Agent": "wejot-agent-plugin/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as output:
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                received += len(chunk)
                if received > expected_size:
                    raise PullError("SIZE_MISMATCH", "download exceeds bundle_size_bytes")
                digest.update(chunk)
                output.write(chunk)
    except PullError:
        raise
    except (OSError, urllib.error.URLError) as exc:
        raise PullError("DOWNLOAD_FAILED", "bundle download failed") from exc

    if received != expected_size:
        raise PullError("SIZE_MISMATCH", "download size does not match bundle_size_bytes")
    return digest.hexdigest()


def _validate_zip_info(info: zipfile.ZipInfo) -> None:
    name = info.filename
    path = PurePosixPath(name)
    mode = (info.external_attr >> 16) & 0o170000
    if (
        info.is_dir()
        or name.startswith(("/", "\\"))
        or "\\" in name
        or path.is_absolute()
        or len(path.parts) != 1
        or ".." in path.parts
        or mode == stat.S_IFLNK
    ):
        raise PullError("UNEXPECTED_ZIP_ENTRY", "bundle contains an unsafe ZIP entry")


def _extract_bundle(zip_path: Path, staging_dir: Path, max_uncompressed_bytes: int) -> None:
    try:
        with zipfile.ZipFile(zip_path) as archive:
            infos = archive.infolist()
            for info in infos:
                _validate_zip_info(info)
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or set(names) != set(ARTIFACT_FILES):
                raise PullError(
                    "UNEXPECTED_ZIP_ENTRY",
                    "bundle must contain exactly the four survey artifact files",
                )
            total_uncompressed = sum(info.file_size for info in infos)
            if total_uncompressed > max_uncompressed_bytes:
                raise PullError("INVALID_ZIP", "bundle uncompressed content is too large")
            staging_dir.mkdir(parents=True, exist_ok=True)
            for filename in ARTIFACT_FILES:
                target = staging_dir / filename
                with archive.open(filename) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=CHUNK_SIZE)
    except PullError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise PullError("INVALID_ZIP", "bundle is not a valid ZIP archive") from exc


def _materialize(staging_dir: Path, output_dir: Path, force: bool, backup_dir: Path) -> None:
    existing = [filename for filename in ARTIFACT_FILES if (output_dir / filename).exists()]
    if existing and not force:
        raise PullError("LOCAL_FILES_EXIST", "local survey artifact files already exist: " + ", ".join(existing))

    backup_dir.mkdir(parents=True, exist_ok=True)
    for filename in existing:
        target = output_dir / filename
        if not target.is_file():
            raise PullError("WRITE_FAILED", "an artifact target exists and is not a regular file")
        shutil.copy2(target, backup_dir / filename)

    replaced: list[str] = []
    try:
        for filename in ARTIFACT_FILES:
            os.replace(staging_dir / filename, output_dir / filename)
            replaced.append(filename)
    except OSError as exc:
        for filename in reversed(replaced):
            target = output_dir / filename
            backup = backup_dir / filename
            try:
                if backup.exists():
                    os.replace(backup, target)
                elif target.exists():
                    target.unlink()
            except OSError:
                pass
        raise PullError("WRITE_FAILED", "failed to write survey artifact files") from exc


def pull_bundle(
    *,
    url: str,
    expected_sha256: str,
    expected_size: int,
    output_dir: Path,
    force: bool = False,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> dict[str, object]:
    output_dir = output_dir.resolve()
    _validate_inputs(url, expected_sha256, expected_size, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".wejot-pull-", dir=output_dir.parent) as temporary:
        temporary_dir = Path(temporary)
        zip_path = temporary_dir / "bundle.zip"
        actual_sha256 = _download(url, zip_path, expected_size)
        if actual_sha256 != expected_sha256.lower():
            raise PullError("SHA256_MISMATCH", "bundle SHA-256 does not match bundle_sha256")
        staging_dir = temporary_dir / "staging"
        _extract_bundle(zip_path, staging_dir, max_uncompressed_bytes)
        _materialize(staging_dir, output_dir, force, temporary_dir / "backup")
    return {
        "success": True,
        "output_dir": str(output_dir),
        "bundle_size_bytes": expected_size,
        "written": list(ARTIFACT_FILES),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download and materialize a WeJot survey bundle")
    parser.add_argument("--url", required=True, help="bundle_download_url returned by MCP")
    parser.add_argument("--sha256", required=True, help="bundle_sha256 returned by MCP")
    parser.add_argument("--size-bytes", required=True, type=int, help="bundle_size_bytes returned by MCP")
    parser.add_argument("--output-dir", required=True, type=Path, help="survey workspace directory")
    parser.add_argument("--force", action="store_true", help="replace existing artifact files")
    parser.add_argument(
        "--max-uncompressed-bytes",
        type=int,
        default=DEFAULT_MAX_UNCOMPRESSED_BYTES,
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = pull_bundle(
            url=args.url,
            expected_sha256=args.sha256,
            expected_size=args.size_bytes,
            output_dir=args.output_dir,
            force=args.force,
            max_uncompressed_bytes=args.max_uncompressed_bytes,
        )
    except PullError as exc:
        print(json.dumps({"success": False, "error": exc.code, "message": exc.message}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
