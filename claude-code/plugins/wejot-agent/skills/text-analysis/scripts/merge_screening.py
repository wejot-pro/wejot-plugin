#!/usr/bin/env python3
"""
合并 VOC 初筛结果。
将所有 batch screened 文件合并为一份 screened_voc.csv。
"""

import argparse
import csv
import json
import sys
from pathlib import Path


def merge_screening(results_dir: str, output_file: str) -> dict:
    results_path = Path(results_dir)
    if not results_path.exists():
        return {"success": False, "error": f"结果目录不存在: {results_dir}"}

    result_files = sorted(results_path.glob("batch_*_screened.csv"))
    if not result_files:
        return {"success": False, "error": f"在 {results_dir} 中未找到初筛结果文件"}

    all_rows = []
    headers = None
    errors = []

    for f in result_files:
        try:
            with open(f, "r", encoding="utf-8-sig") as fp:
                reader = csv.DictReader(fp)
                if headers is None:
                    headers = reader.fieldnames or []
                rows = list(reader)
                all_rows.extend(rows)
        except Exception as e:
            errors.append(f"读取 {f.name} 失败: {e}")

    if not all_rows:
        return {"success": False, "error": "所有文件读取失败", "details": errors}

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=headers)
        writer.writeheader()
        writer.writerows(all_rows)

    return {
        "success": True,
        "total_rows": len(all_rows),
        "batch_count": len(result_files),
        "columns": headers,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description="合并 VOC 初筛结果")
    parser.add_argument("--results-dir", required=True, help="batch screened 文件所在目录")
    parser.add_argument("--output", required=True, help="合并后的输出文件路径")
    args = parser.parse_args()

    result = merge_screening(args.results_dir, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
