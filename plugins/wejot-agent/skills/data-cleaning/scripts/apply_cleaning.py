#!/usr/bin/env python3
"""确定性清洗执行 - data-cleaning 步骤 3。

读入数据 + 已确认的 rules_config.json，执行"脚本确定性"类规则，
输出：清洗后数据 / 审计日志 / 命中统计。在数据副本上操作，从不改原始文件。

仅处理脚本侧规则：G1 G2 G5 S1 S2 S3 S4 DUP。
LLM 判断层规则（S5 / 业务矛盾 / 内容相似度）不在此处。

用法:
    apply_cleaning.py <data_file> --rules rules_config.json --outdir out/

输出 out/: cleaned_data.csv, audit_log.json, summary.json

约定:
- disposition=hard_remove 且 meta.auto_apply=false → 只标记 (marked_hard_remove)，不删除
- disposition=hard_remove 且 auto_apply=true        → 从 cleaned_data 移除
- disposition=flag                                  → 仅标记，待人工复核
- 依赖元数据缺失的规则自动跳过并记入 summary.skipped
"""
import sys
import ast
import json
import argparse
import operator
from pathlib import Path


# ---------- 安全表达式求值（S4 人口画像矛盾用）----------
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Mod: operator.mod}
_CMP = {ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Lt: operator.lt,
        ast.LtE: operator.le, ast.Eq: operator.eq, ast.NotEq: operator.ne}
_SAFE_FUNCS = {"abs": abs, "len": len}


def _eval(node, row):
    if isinstance(node, ast.Expression):
        return _eval(node.body, row)
    if isinstance(node, ast.BoolOp):
        vals = [_eval(v, row) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval(node.operand, row)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval(node.operand, row)
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_eval(node.left, row), _eval(node.right, row))
    if isinstance(node, ast.Compare):
        left = _eval(node.left, row)
        for op, comp in zip(node.ops, node.comparators):
            right = _eval(comp, row)
            if isinstance(op, ast.Is) or isinstance(op, ast.IsNot):
                res = (left is right) if isinstance(op, ast.Is) else (left is not right)
            else:
                if left is None or right is None:
                    return False
                res = _CMP[type(op)](left, right)
            if not res:
                return False
            left = right
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fn = _SAFE_FUNCS.get(node.func.id)
        if fn is None:
            raise ValueError(f"不允许的函数: {node.func.id}")
        return fn(*[_eval(a, row) for a in node.args])
    if isinstance(node, ast.Name):
        if node.id == "null" or node.id == "None":
            return None
        return row.get(node.id)
    if isinstance(node, ast.Constant):
        return node.value
    raise ValueError(f"不允许的表达式节点: {type(node).__name__}")


def safe_eval(expr, row):
    """对单行 row(dict) 求值布尔表达式；任何异常视为不命中(False)。"""
    try:
        # 兼容 schema 里的 "x not null" 写法 -> "x is not None"
        norm = expr.replace(" not null", " is not None").replace(" is null", " is None")
        tree = ast.parse(norm, mode="eval")
        return bool(_eval(tree, row))
    except Exception:
        return False


# ---------- 工具 ----------
def load_data(path):
    import pandas as pd
    suf = Path(path).suffix.lower()
    if suf == ".json":
        return pd.read_json(path)
    if suf in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if suf in (".csv", ".txt", ".tsv", ".md", ""):
        return read_delimited(path, pd)
    sys.exit(f"不支持的文件类型: {suf}")


def read_delimited(path, pd):
    """读取 csv/tsv/txt/markdown 表：自动识别分隔符；支持 markdown 管道表（去分隔行、去重复表头）。"""
    import io
    import re as _re
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    pipe_lines = [ln for ln in lines if ln.count("|") >= 2]
    if len(pipe_lines) >= 2:
        rows = []
        header = None
        for ln in pipe_lines:
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if all(_re.fullmatch(r"[:\-\s]*", c or "") for c in cells):
                continue
            if header is None:
                header = cells
            elif cells == header:
                continue
            else:
                rows.append(cells)
        if header and rows:
            ncol = len(header)
            data = [(r[:ncol] + [""] * (ncol - len(r))) for r in rows]
            return pd.DataFrame(data, columns=header)
    try:
        return pd.read_csv(io.StringIO(text), sep=None, engine="python")
    except Exception:
        return pd.read_csv(io.StringIO(text))


class Audit:
    def __init__(self):
        self.records = []
        self.hits = {}      # rule_id -> 命中样本数

    def add(self, rid, idval, field, evidence, disposition, applied):
        self.records.append({
            "id": idval, "rule_id": rid, "field": field,
            "evidence": evidence, "disposition": disposition, "applied": applied,
        })
        self.hits[rid] = self.hits.get(rid, 0) + 1


# ---------- 各规则处理器 ----------
def disposition_of(rule, auto_apply):
    """返回 (是否真删, 审计中记录的 disposition 标签)。"""
    d = rule.get("disposition", "flag")
    if d == "hard_remove":
        return (auto_apply, "removed_hard" if auto_apply else "marked_hard_remove")
    return (False, "flag")


def rule_G1(df, rule, ctx, audit):
    import pandas as pd  # noqa
    p = rule.get("params", {})
    q_cols = ctx["q_cols"]
    min_rate = p.get("min_answer_rate", 0.6)
    required = p.get("required_fields", [])
    do_remove, tag = disposition_of(rule, ctx["auto_apply"])
    for idx, row in df.iterrows():
        idval = row.get(ctx["id_field"], idx)
        # 必答缺失
        miss_req = [c for c in required if c in df.columns and pd.isna(row[c])]
        if miss_req:
            audit.add("G1", idval, ",".join(miss_req), "必答题为空", tag, do_remove)
            if do_remove:
                ctx["to_drop"].add(idx)
            continue
        # 整体答题率
        if q_cols:
            rate = row[q_cols].notna().mean()
            if rate < min_rate:
                audit.add("G1", idval, "answer_rate",
                          f"答题率{rate:.2f}<{min_rate}", "flag", False)


def rule_G2(df, rule, ctx, audit):
    p = rule.get("params", {})
    do_remove, tag = disposition_of(rule, ctx["auto_apply"])
    for idx, row in df.iterrows():
        idval = row.get(ctx["id_field"], idx)
        for col, spec in p.items():
            if col not in df.columns:
                continue
            val = row[col]
            if val is None or (isinstance(val, float) and val != val):
                continue
            bad = False
            if spec.get("type") == "number":
                try:
                    v = float(val)
                    if ("min" in spec and v < spec["min"]) or ("max" in spec and v > spec["max"]):
                        bad = True
                except (ValueError, TypeError):
                    bad = True
            elif spec.get("type") == "choice":
                codes = spec.get("valid_codes", [])
                if codes and val not in codes:
                    bad = True
            if bad:
                audit.add("G2", idval, col, f"值={val} 越界", tag, do_remove)
                if do_remove:
                    ctx["to_drop"].add(idx)


def rule_G5(df, rule, ctx, audit):
    import pandas as pd
    p = rule.get("params", {})
    factor = p.get("factor", 1.5)
    method = p.get("method", "iqr")
    for col in (rule.get("target") or []):
        if col not in df.columns or not pd.api.types.is_numeric_dtype(df[col]):
            continue
        s = df[col].dropna()
        if len(s) < 4:
            continue
        if method == "iqr":
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            lo, hi = q1 - factor * iqr, q3 + factor * iqr
        else:  # zscore
            mu, sd = s.mean(), s.std()
            lo, hi = mu - factor * sd, mu + factor * sd
        for idx, val in df[col].items():
            if pd.notna(val) and (val < lo or val > hi):
                idval = df.at[idx, ctx["id_field"]] if ctx["id_field"] in df.columns else idx
                audit.add("G5", idval, col, f"值={val} 超出[{lo:.1f},{hi:.1f}]", "flag", False)


def rule_S1(df, rule, ctx, audit):
    import pandas as pd
    if not ctx["meta_avail"].get("duration"):
        ctx["skipped"].append("S1 速答：缺答题时长")
        return
    dcol = ctx["meta_cols"].get("duration")
    p = rule.get("params", {})
    item_count = p.get("item_count", len(ctx["q_cols"]) or 1)
    med = p.get("median_per_item_sec") or float(df[dcol].median()) / max(item_count, 1)
    floor = item_count * med * p.get("total_duration_factor", 0.4)
    for idx, val in df[dcol].items():
        if pd.notna(val) and val < floor:
            idval = df.at[idx, ctx["id_field"]] if ctx["id_field"] in df.columns else idx
            audit.add("S1", idval, dcol, f"总时长{val}s<{floor:.0f}s", "flag", False)


def rule_S2(df, rule, ctx, audit):
    import pandas as pd
    p = rule.get("params", {})
    thr = p.get("same_col_ratio", 0.95)
    for grp in (rule.get("target") or []):
        # target 可为单列或矩阵题前缀；这里按"同前缀的列组"识别
        cols = [c for c in df.columns if c == grp or c.startswith(grp)]
        if len(cols) < 2:
            continue
        for idx, row in df[cols].iterrows():
            vals = row.dropna().tolist()
            if not vals:
                continue
            top = max(set(vals), key=vals.count)
            ratio = vals.count(top) / len(vals)
            if ratio >= thr:
                idval = df.at[idx, ctx["id_field"]] if ctx["id_field"] in df.columns else idx
                audit.add("S2", idval, grp, f"直线占比{ratio:.0%}(值={top})", "flag", False)


def rule_S3(df, rule, ctx, audit):
    import pandas as pd
    p = rule.get("params", {})
    do_remove, tag = disposition_of(rule, ctx["auto_apply"])
    for idx, row in df.iterrows():
        idval = row.get(ctx["id_field"], idx)
        for logic in p.get("skip_logic", []):
            cond = logic.get("if", {})
            triggered = all(row.get(k) == v for k, v in cond.items())
            if triggered:
                for skipped in logic.get("then_skip", []):
                    if skipped in df.columns and pd.notna(row[skipped]):
                        audit.add("S3", idval, skipped,
                                  f"应跳过却有答案(因{cond})", tag, do_remove)
                        if do_remove:
                            ctx["to_drop"].add(idx)


def rule_S4(df, rule, ctx, audit):
    p = rule.get("params", {})
    for idx, row in df.iterrows():
        idval = row.get(ctx["id_field"], idx)
        # NaN(float) 归一成 None，否则 "x is not None" 会对空值误判为真
        rowd = {k: (None if (isinstance(v, float) and v != v) else v)
                for k, v in row.to_dict().items()}
        rowd.update(ctx["derived"])  # 注入派生量如 survey_year
        for chk in p.get("checks", []):
            if safe_eval(chk["expr"], rowd):
                severity = chk.get("severity", "hard")
                if severity == "hard":
                    do_remove = ctx["auto_apply"]
                    tag = "removed_hard" if do_remove else "marked_hard_remove"
                else:
                    do_remove, tag = False, "flag"
                audit.add("S4", idval, chk.get("name", "矛盾"),
                          f"命中:{chk['expr']}", tag, do_remove)
                if do_remove:
                    ctx["to_drop"].add(idx)


def rule_DUP(df, rule, ctx, audit):
    import pandas as pd
    p = rule.get("params", {})
    mc = ctx["meta_cols"]
    # userid 级
    ud = p.get("userid_duplicate")
    if ud and ctx["meta_avail"].get("userid"):
        ucol = mc["userid"]
        keep = ud.get("keep", "first")
        do_remove = ctx["auto_apply"] and ud.get("disposition") == "hard_remove"
        dup_mask = df.duplicated(subset=[ucol], keep=keep)
        for idx in df.index[dup_mask]:
            idval = df.at[idx, ctx["id_field"]] if ctx["id_field"] in df.columns else idx
            tag = "removed_hard" if do_remove else "marked_hard_remove"
            audit.add("DUP", idval, ucol, f"userid重复(保留{keep})", tag, do_remove)
            if do_remove:
                ctx["to_drop"].add(idx)
    elif ud:
        ctx["skipped"].append("DUP userid：缺 userid 列")
    # 组合信号（ip+ua+时间窗）→ 只标记疑似，交 LLM 比对内容
    combo = p.get("combo_signal")
    if combo:
        fields = [mc.get(f) for f in combo.get("fields", []) if ctx["meta_avail"].get(f)]
        if len(fields) == len(combo.get("fields", [])) and fields:
            grouped = df.groupby(fields, dropna=True)
            for _, g in grouped:
                if len(g) > 1:
                    for idx in g.index:
                        idval = df.at[idx, ctx["id_field"]] if ctx["id_field"] in df.columns else idx
                        audit.add("DUP", idval, "+".join(fields),
                                  f"{'+'.join(fields)}相同组(n={len(g)})，待内容比对", "flag", False)
        else:
            ctx["skipped"].append("DUP 组合信号：缺 ip/ua 列，降级")


HANDLERS = {"G1": rule_G1, "G2": rule_G2, "G5": rule_G5, "S1": rule_S1,
            "S2": rule_S2, "S3": rule_S3, "S4": rule_S4, "DUP": rule_DUP}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_file")
    ap.add_argument("--rules", required=True)
    ap.add_argument("--outdir", default="cleaning_out")
    args = ap.parse_args()

    cfg = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    df = load_data(args.data_file)
    meta = cfg.get("meta", {})
    id_field = cfg.get("id_field", "")
    meta_avail = meta.get("metadata_available", {})
    meta_cols = (meta.get("metadata_columns") or {})

    meta_col_set = {v for v in meta_cols.values() if v}
    q_cols = [c for c in df.columns if c not in meta_col_set and c != id_field]

    ctx = {
        "id_field": id_field, "auto_apply": bool(meta.get("auto_apply", False)),
        "meta_avail": meta_avail, "meta_cols": meta_cols, "q_cols": q_cols,
        "to_drop": set(), "skipped": [],
        "derived": {"survey_year": meta.get("survey_year")},
    }

    audit = Audit()
    for rule in cfg.get("rules", []):
        if not rule.get("enabled", True):
            continue
        h = HANDLERS.get(rule.get("rule_id"))
        if h is None:
            ctx["skipped"].append(f"{rule.get('rule_id')}: 非脚本侧规则或未实现，跳过")
            continue
        h(df, rule, ctx, audit)

    # 生成清洗后数据（真删的移除；标记类保留并加列）
    cleaned = df.drop(index=list(ctx["to_drop"])).copy()
    flagged_ids = {r["id"] for r in audit.records if r["disposition"] != "removed_hard"}
    if id_field in cleaned.columns:
        cleaned["_flagged"] = cleaned[id_field].isin(flagged_ids)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(outdir / "cleaned_data.csv", index=False)
    (outdir / "audit_log.json").write_text(
        json.dumps(audit.records, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "n_input": len(df),
        "n_removed": len(ctx["to_drop"]),
        "n_output": len(cleaned),
        "n_flagged_pending": len(flagged_ids),
        "hits_by_rule": audit.hits,
        "skipped": ctx["skipped"],
    }
    (outdir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ 清洗完成 → {outdir}/")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
