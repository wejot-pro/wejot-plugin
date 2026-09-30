#!/usr/bin/env python3
"""
报告数据准备脚本。
从 analysis_results.csv 生成统计摘要，供 Document Skill 生成 HTML 报告使用。
使用标准库 csv + collections，无需 pandas。
"""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path


def read_csv(filename):
    with open(filename, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader), reader.fieldnames or []


def to_numeric(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def generate_report_data(input_file: str, plan_file: str, output_file: str) -> dict:
    rows, cols = read_csv(input_file)
    plan_rows, _ = read_csv(plan_file)

    if not rows:
        return {"success": False, "error": "分析结果为空"}

    total = len(rows)
    summary = {"total": total, "dimensions": {}}

    for dim in plan_rows:
        col = dim.get("dimension_name", "").strip()
        dim_type = dim.get("dimension_type", "").strip()
        if not col or col not in cols:
            continue

        dim_stats = {
            "type": dim_type,
            "description": dim.get("description", ""),
        }

        values = [r.get(col, "").strip() for r in rows if r.get(col, "").strip()]

        if dim_type == "enum":
            counts = Counter(values)
            dim_stats["distribution"] = {
                k: {"count": v, "percentage": round(v / total * 100, 2)}
                for k, v in counts.most_common()
            }
            dim_stats["top"] = [k for k, _ in counts.most_common(3)]

        elif dim_type == "score":
            nums = [v for v in (to_numeric(v) for v in values) if v is not None]
            if nums:
                dim_stats["stats"] = {
                    "mean": round(sum(nums) / len(nums), 2),
                    "median": round(sorted(nums)[len(nums) // 2], 2),
                    "min": round(min(nums), 2),
                    "max": round(max(nums), 2),
                }
                # 分箱分布
                try:
                    range_str = str(dim.get("options_or_range", "")).strip()
                    if "-" in range_str:
                        parts = range_str.split("-")
                        min_v = int(float(parts[0].strip()))
                        max_v = int(float(parts[1].strip()))
                        bins = {str(i): 0 for i in range(min_v, max_v + 1)}
                        for v in nums:
                            key = str(int(v))
                            if key in bins:
                                bins[key] += 1
                        dim_stats["distribution"] = bins
                except Exception:
                    pass

        elif dim_type == "boolean":
            counts = Counter(values)
            dim_stats["distribution"] = {
                k: {"count": v, "percentage": round(v / total * 100, 2)}
                for k, v in counts.most_common()
            }

        elif dim_type == "text":
            dim_stats["sample_count"] = len(values)
            dim_stats["examples"] = values[:5]

        summary["dimensions"][col] = dim_stats

    # 典型样例：按第一个 enum 维度分组抽样
    examples = []
    enum_cols = [d.get("dimension_name", "").strip() for d in plan_rows if d.get("dimension_type", "").strip() == "enum"]
    if enum_cols:
        group_col = enum_cols[0]
        seen_values = set()
        for r in rows:
            val = r.get(group_col, "").strip()
            if val and val not in seen_values and len(examples) < 15:
                seen_values.add(val)
                example = {"id": r.get("id", ""), "content": r.get("content", "")}
                for c in cols:
                    if c not in ("id", "content"):
                        example[c] = r.get(c, "")
                examples.append(example)
        # 补充更多样例
        for r in rows:
            if len(examples) >= 15:
                break
            example = {"id": r.get("id", ""), "content": r.get("content", "")}
            for c in cols:
                if c not in ("id", "content"):
                    example[c] = r.get(c, "")
            if example not in examples:
                examples.append(example)

    summary["examples"] = examples[:15]

    # 写入输出
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return {
        "success": True,
        "total": total,
        "dimensions_count": len(summary["dimensions"]),
        "examples_count": len(examples),
    }


def main():
    parser = argparse.ArgumentParser(description="生成报告数据")
    parser.add_argument("--input", required=True, help="analysis_results.csv 路径")
    parser.add_argument("--plan", required=True, help="analysis_plan.csv 路径")
    parser.add_argument("--output", required=True, help="report_data.json 输出路径")
    args = parser.parse_args()

    result = generate_report_data(args.input, args.plan, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
