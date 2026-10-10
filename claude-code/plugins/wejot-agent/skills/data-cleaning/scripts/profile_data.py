#!/usr/bin/env python3
"""问卷数据画像 - data-cleaning 步骤 1。

体检数据质量并检查元数据可用性，为规则生成提供依据。
不修改数据，只读统计。

用法:
    profile_data.py <data_file> [--meta meta.json] [--out profile.json]

data_file: .csv / .json / .xlsx（首选 csv/json，xlsx 需 openpyxl）
--meta:    可选，列名映射与题型声明，见下方 META 结构；缺省则自动启发式探测元数据列
--out:     画像 JSON 输出路径；缺省打印到 stdout

META 结构 (meta.json):
    {
      "id_field": "response_id",
      "metadata_columns": {            # 把语义元数据映射到实际列名
        "userid": "user_id", "ip": "ip_addr", "ua": "user_agent",
        "submit_time": "submitted_at", "duration": "total_seconds"
      },
      "question_columns": ["q1","q2",...]   # 题目列；缺省=非元数据列
    }
"""
import sys
import json
import argparse
from pathlib import Path

# 元数据语义键 -> 启发式候选列名（小写匹配）
META_CANDIDATES = {
    "userid": ["userid", "user_id", "uid", "openid", "respondent_id"],
    "ip": ["ip", "ip_addr", "ipaddress", "client_ip"],
    "ua": ["ua", "user_agent", "useragent"],
    "submit_time": ["submit_time", "submitted_at", "submittime", "create_time", "finish_time"],
    "duration": ["duration", "durationseconds", "duration_seconds", "total_seconds", "answer_time", "elapsed", "use_time"],
}


def load_data(path):
    p = Path(path)
    suf = p.suffix.lower()
    try:
        import pandas as pd
    except ImportError:
        sys.exit("需要 pandas：pip install pandas")
    if suf == ".json":
        return pd.read_json(p)
    if suf in (".xlsx", ".xls"):
        return pd.read_excel(p)
    # csv / txt / tsv / md / 无后缀：统一走可识别分隔符与 markdown 管道表的读取
    if suf in (".csv", ".txt", ".tsv", ".md", ""):
        return read_delimited(p, pd)
    sys.exit(f"不支持的文件类型: {suf}")


def read_delimited(p, pd):
    """读取 csv/tsv/txt/markdown 表：自动识别分隔符；支持 markdown 管道表（去分隔行、去重复表头）。"""
    import io
    import re as _re
    text = Path(p).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    # markdown / 管道表：含多个 | 的行
    pipe_lines = [ln for ln in lines if ln.count("|") >= 2]
    if len(pipe_lines) >= 2:
        rows = []
        header = None
        for ln in pipe_lines:
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if all(_re.fullmatch(r"[:\-\s]*", c or "") for c in cells):
                continue  # 表头分隔行 |---|:--|
            if header is None:
                header = cells
            elif cells == header:
                continue  # 分页重复表头
            else:
                rows.append(cells)
        if header and rows:
            ncol = len(header)
            data = [(r[:ncol] + [""] * (ncol - len(r))) for r in rows]
            return pd.DataFrame(data, columns=header)
    # 退回：自动识别分隔符（逗号/制表/分号等）
    try:
        return pd.read_csv(io.StringIO(text), sep=None, engine="python")
    except Exception:
        return pd.read_csv(io.StringIO(text))


def detect_metadata(df, meta):
    """返回 {语义键: 实际列名 or None}。优先用 meta 映射，否则启发式。"""
    mapping = (meta or {}).get("metadata_columns", {}) or {}
    cols_lower = {c.lower(): c for c in df.columns}
    resolved = {}
    for key, candidates in META_CANDIDATES.items():
        if key in mapping and mapping[key] in df.columns:
            resolved[key] = mapping[key]
            continue
        found = None
        for cand in candidates:
            if cand in cols_lower:
                found = cols_lower[cand]
                break
        resolved[key] = found
    return resolved


def limited_capabilities(meta_resolved):
    """据缺失元数据列出受限的检测能力。"""
    limits = []
    if not meta_resolved.get("duration"):
        limits.append("缺『答题时长』→ 速答(S1) 不可用")
    if not meta_resolved.get("userid"):
        limits.append("缺『userid』→ 账号级重复(DUP) 降级")
    if not (meta_resolved.get("ip") and meta_resolved.get("ua")):
        limits.append("缺『ip 或 ua』→ 组合重复信号(DUP) 降级")
    if not meta_resolved.get("submit_time"):
        limits.append("缺『提交时间』→ 时间窗聚集判定不可用")
    return limits


def profile(df, meta):
    import pandas as pd  # noqa
    meta = meta or {}
    meta_resolved = detect_metadata(df, meta)
    meta_cols = {v for v in meta_resolved.values() if v}
    id_field = meta.get("id_field")
    q_cols = meta.get("question_columns") or [
        c for c in df.columns if c not in meta_cols and c != id_field
    ]

    n = len(df)
    # 各题缺失率 + 答案分布摘要
    questions = {}
    for c in q_cols:
        s = df[c]
        miss = float(s.isna().mean())
        col = {"missing_rate": round(miss, 4), "n_unique": int(s.nunique(dropna=True))}
        if pd.api.types.is_numeric_dtype(s):
            d = s.dropna()
            if len(d):
                col["numeric"] = {
                    "min": float(d.min()), "max": float(d.max()),
                    "mean": round(float(d.mean()), 3), "median": float(d.median()),
                }
        else:
            vc = s.dropna().astype(str).value_counts().head(8)
            col["top_values"] = {k: int(v) for k, v in vc.items()}
        questions[c] = col

    # 单份有效答题率分布（非元数据题列的非空占比）
    if q_cols:
        answer_rate = df[q_cols].notna().mean(axis=1)
        rate_summary = {
            "mean": round(float(answer_rate.mean()), 4),
            "p10": round(float(answer_rate.quantile(0.10)), 4),
            "below_0.6": int((answer_rate < 0.6).sum()),
        }
    else:
        rate_summary = None

    # 答题时长分布
    dur_summary = None
    dcol = meta_resolved.get("duration")
    if dcol and pd.api.types.is_numeric_dtype(df[dcol]):
        d = df[dcol].dropna()
        if len(d):
            dur_summary = {
                "median_sec": float(d.median()),
                "p5_sec": float(d.quantile(0.05)),
                "min_sec": float(d.min()),
            }

    return {
        "n_responses": n,
        "id_field": id_field,
        "metadata_available": {k: bool(v) for k, v in meta_resolved.items()},
        "metadata_columns_resolved": meta_resolved,
        "limited_capabilities": limited_capabilities(meta_resolved),
        "question_count": len(q_cols),
        "answer_rate": rate_summary,
        "duration": dur_summary,
        "questions": questions,
    }


def classify_question(series, pd):
    """粗分题型：numeric / structured(JSON选项) / text(开放题) / categorical。

    开放题判定靠『唯一度高 + 答案有一定长度』，不用绝对 nun 阈值（小样本下会误伤）。
    """
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    s = series.dropna().astype(str).str.strip()
    s = s[s != ""]
    n = len(s)
    if n == 0:
        return "empty"
    if s.str.startswith(("{", "[")).mean() > 0.5:
        return "structured"
    ratio = s.nunique() / n
    avg_len = float(s.str.len().mean())
    # 高唯一度且答案不太短 → 开放题；或平均很长（无论唯一度）→ 开放题
    if (ratio >= 0.7 and avg_len >= 6) or avg_len >= 12:
        return "text"
    return "categorical"


def emit_structure_and_next_steps(df, result, out_path):
    """渐进式披露：抽题目结构 → survey_structure.json；每个开放题答案 → open_<qid>.csv；
    并打印 Step 2 的语义复核任务说明，供宿主按可用能力并行或顺序执行。"""
    import pandas as pd
    out_dir = Path(out_path).resolve().parent if out_path else Path(".").resolve()
    (out_dir / "clean_judge").mkdir(exist_ok=True)
    id_field = result.get("id_field")
    q_cols = list(result.get("questions", {}).keys())

    questions = []
    open_text = []  # [(qid, 题干, col)]
    for i, col in enumerate(q_cols, 1):
        qid = f"q{i}"
        qtype = classify_question(df[col], pd)
        samples = df[col].dropna().astype(str)
        samples = samples[samples.str.strip() != ""].head(3).tolist()
        questions.append({"question_id": qid, "题干": col, "题型": qtype, "样例": samples})
        if qtype == "text":
            open_text.append((qid, col, col))

    structure = {"id_field": id_field, "questions": questions,
                 "open_text_questions": [q for q, _, _ in open_text]}
    (out_dir / "survey_structure.json").write_text(
        json.dumps(structure, ensure_ascii=False, indent=2), encoding="utf-8")

    # 导出每个开放题的答案文件，供 Step 4 逐题派 subagent
    exported = []  # [(qid, 题干, filename)]
    if id_field and id_field in df.columns:
        for qid, 题干, col in open_text:
            sub = df[[id_field, col]].copy()
            sub.columns = ["response_id", "answer"]
            sub.to_csv(out_dir / f"open_{qid}.csv", index=False)
            exported.append((qid, 题干, f"open_{qid}.csv"))

    od = str(out_dir)
    print()
    print("✅ 题目结构已写入 survey_structure.json（共 %d 题，开放题 %d 个：%s）"
          % (len(questions), len(open_text), ", ".join(q for q, _, _ in open_text) or "无"))
    if exported:
        print("✅ 已为每个开放题导出答案文件：" + ", ".join(n for _, _, n in exported))
    print()
    print("========== 下一步：Step 2（规则生成与确认，关卡）请照此执行 ==========")
    print("⚠️ 业务逻辑矛盾、开放题质检属【语义判断】；应与确定性脚本检查分开，并保留结构化审计。")
    print()
    print("① 检查 survey_structure.json 的题目逻辑，列出可能互斥的候选题对；此步只看题目结构，不扫描样本。")
    print("   建议结果字段：pair_id/question_a/question_b/逻辑说明/建议处置。")
    if exported:
        print()
        print("② 开放题质检（待用户确认规则后，Step 4 执行）——按开放题独立分片，宿主可并行处理：")
        for qid, 题干, name in exported:
            t = 题干 if len(题干) <= 30 else 题干[:30]
            print("   - " + qid + "『" + t + "』：" + od + "/" + name
                  + "；判断乱填/复制/答非所问，先脱敏不必要的个人信息，保留 response_id/verdict/confidence/evidence。")
    print()
    print("③ 把上面的逻辑矛盾候选 + 脚本类规则（速答/直线/值域/去重… 见 cleaning-rules.md）整理成《规则清单》，向用户确认后才进入 Step 3 清洗。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_file")
    ap.add_argument("--meta")
    ap.add_argument("--out")
    args = ap.parse_args()

    meta = json.loads(Path(args.meta).read_text(encoding="utf-8")) if args.meta else {}
    df = load_data(args.data_file)
    result = profile(df, meta)

    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
        print(f"✅ 画像已写入 {args.out}")
        if result["limited_capabilities"]:
            print("⚠️ 受限能力：")
            for x in result["limited_capabilities"]:
                print("  -", x)
        emit_structure_and_next_steps(df, result, args.out)
    else:
        print(out)


if __name__ == "__main__":
    main()
