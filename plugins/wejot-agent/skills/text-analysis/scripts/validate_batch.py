#!/usr/bin/env python3
"""
批量分析结果验收脚本。
验证 SubAgent 输出的 batch_result.csv 是否符合规范。
使用标准库 csv，无需 pandas。
"""

import argparse
import csv
import json
import sys


def read_csv_dict(filename):
    """读取 CSV 为字典列表，同时返回表头。"""
    with open(filename, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return rows, reader.fieldnames or []


def validate_batch(input_file: str, output_file: str, plan_file: str) -> tuple[bool, list[str]]:
    """验证单个 batch 的输出质量。"""
    errors = []

    try:
        input_rows, input_cols = read_csv_dict(input_file)
    except Exception as e:
        return False, [f"无法读取输入文件: {e}"]

    try:
        output_rows, output_cols = read_csv_dict(output_file)
    except Exception as e:
        return False, [f"无法读取输出文件: {e}"]

    try:
        plan_rows, _ = read_csv_dict(plan_file)
    except Exception as e:
        return False, [f"无法读取分析计划: {e}"]

    # 1. 行数检查
    if len(input_rows) != len(output_rows):
        errors.append(
            f"行数不匹配: 输入 {len(input_rows)} 行 != 输出 {len(output_rows)} 行"
        )

    # 2. 原始列保留检查
    for col in input_cols:
        if col not in output_cols:
            errors.append(f"原始列 '{col}' 在输出中被删除")

    # 3. ID 列一致性检查
    if "id" in input_cols and "id" in output_cols:
        input_ids = [r.get("id") for r in input_rows]
        output_ids = [r.get("id") for r in output_rows]
        if input_ids != output_ids:
            errors.append("ID 列不一致（顺序或内容被修改）")

    # 4. 分析列完整性 + 空值检查
    for dim in plan_rows:
        col = dim.get("dimension_name", "").strip()
        if not col:
            continue
        if col not in output_cols:
            errors.append(f"缺少分析列 '{col}'")
            continue

        null_count = sum(1 for r in output_rows if not r.get(col, "").strip())
        if null_count > 0:
            errors.append(f"列 '{col}' 有 {null_count} 个空值")

    # 5. 数据类型和范围检查
    for dim in plan_rows:
        col = dim.get("dimension_name", "").strip()
        if not col or col not in output_cols:
            continue

        dim_type = dim.get("dimension_type", "").strip()
        options = dim.get("options_or_range", "")

        if dim_type == "enum":
            valid_values = set(str(v).strip() for v in str(options).split("|") if v.strip())
            if not valid_values:
                continue

            actual_values = set(str(r.get(col, "")).strip() for r in output_rows if str(r.get(col, "")).strip())
            invalid = actual_values - valid_values
            if invalid:
                # 检测是否是因为多值拼接导致（包含 / 或 、分隔符）
                multivalue_hints = [v for v in invalid if "/" in v or "、" in v or "|" in v or "," in v]
                if multivalue_hints:
                    errors.append(
                        f"列 '{col}' 包含非法值: {sorted(invalid)}。"
                        f"注意：enum 类型必须从合法值中精确选择一个单值，禁止拼接多个值。"
                        f"如果文本涉及多个主题，只选最核心/最相关的一个。合法值: {sorted(valid_values)}"
                    )
                else:
                    errors.append(
                        f"列 '{col}' 包含非法值: {sorted(invalid)}，合法值: {sorted(valid_values)}"
                    )

        elif dim_type == "score":
            try:
                range_parts = str(options).split("-")
                if len(range_parts) == 2:
                    min_val = float(range_parts[0].strip())
                    max_val = float(range_parts[1].strip())
                    out_of_range = 0
                    for r in output_rows:
                        val = r.get(col, "").strip()
                        try:
                            fval = float(val)
                            if fval < min_val or fval > max_val:
                                out_of_range += 1
                        except (ValueError, TypeError):
                            out_of_range += 1
                    if out_of_range > 0:
                        errors.append(
                            f"列 '{col}' 有 {out_of_range} 行超出范围 [{min_val}, {max_val}]"
                        )
                else:
                    errors.append(f"列 '{col}' 的范围格式错误: '{options}'，应为 'min-max'")
            except (ValueError, TypeError) as e:
                errors.append(f"列 '{col}' 的范围解析失败: {e}")

        elif dim_type == "boolean":
            valid_bool = {"true", "false", "True", "False", "TRUE", "FALSE", "1", "0", "是", "否", "yes", "no", "Yes", "No", "YES", "NO"}
            actual_values = set(str(r.get(col, "")).strip() for r in output_rows if str(r.get(col, "")).strip())
            invalid = actual_values - valid_bool
            if invalid:
                errors.append(f"列 '{col}' 包含非布尔值: {sorted(invalid)}")

    return len(errors) == 0, errors


def main():
    parser = argparse.ArgumentParser(description="批量分析结果验收")
    parser.add_argument("--input", required=True, help="输入 batch CSV 文件路径")
    parser.add_argument("--output", required=True, help="输出 result CSV 文件路径")
    parser.add_argument("--plan", required=True, help="分析计划 CSV 文件路径")
    args = parser.parse_args()

    ok, errors = validate_batch(args.input, args.output, args.plan)

    result = {
        "passed": ok,
        "errors": errors,
        "input_file": args.input,
        "output_file": args.output,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
