"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    problems: list[str] = []

    # 1. NaN hoặc inf trong pr["metrics"]
    for k, v in pr.get("metrics", {}).items():
        if v is not None:
            try:
                fv = float(v)
                if math.isnan(fv) or math.isinf(fv):
                    problems.append(f"metric {k} is NaN or inf")
            except (ValueError, TypeError):
                pass

    # 2. Số lượng dòng != items x seeds
    m = pr.get("manifest", {})
    expected_count = m.get("items", 0) * len(m.get("seeds", []))
    if len(pr.get("rows", [])) != expected_count:
        problems.append(f"row count {len(pr.get('rows', []))} != expected {expected_count}")

    # 3. Tập (item_id, seed) phải trùng baseline
    pr_pairs = {(r["item_id"], r["seed"]) for r in pr.get("rows", [])}
    base_pairs = {(r["item_id"], r["seed"]) for r in base.get("rows", [])}
    if pr_pairs != base_pairs:
        problems.append("PR (item_id, seed) pairs differ from baseline")

    # 4. Evaluator failures hoặc giá trị None ở metric có chấm điểm
    if pr.get("evaluator_failures"):
        problems.append("evaluator_failures non-empty")
    graded_metrics = [x["id"] for x in spec.get("metrics", []) if x.get("grader") != "lab8.metrics.summarize"]
    for r in pr.get("rows", []):
        for mid in graded_metrics:
            if r.get(mid) is None:
                problems.append(f"row {r.get('item_id')}@{r.get('seed')} has None for {mid}")
                break

    # 5. Nhãn slice của item trong PR khác baseline
    pr_slices = {r["item_id"]: tuple(sorted(r.get("slices") or [])) for r in pr.get("rows", [])}
    base_slices = {r["item_id"]: tuple(sorted(r.get("slices") or [])) for r in base.get("rows", [])}
    if pr_slices != base_slices:
        problems.append("item slice tags differ from baseline")

    # 6. Quy tắc Ratchet: kiểm tra spec có bị nới lỏng so với base_spec
    if base_spec and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        for bm in base_spec.get("metrics", []):
            b_mid = bm["id"]
            pm = next((x for x in spec.get("metrics", []) if x["id"] == b_mid), None)
            if not pm:
                problems.append(f"metric {b_mid} missing from spec")
                continue
            if bm.get("blocking") and not pm.get("blocking"):
                problems.append(f"metric {b_mid} is no longer blocking")
            b_th, p_th = bm.get("threshold", {}), pm.get("threshold", {})
            if "min" in b_th and ("min" not in p_th or p_th["min"] < b_th["min"]):
                problems.append(f"metric {b_mid} min loosened: {p_th.get('min')} < {b_th['min']}")
            if "max" in b_th and ("max" not in p_th or p_th["max"] > b_th["max"]):
                problems.append(f"metric {b_mid} max loosened: {p_th.get('max')} > {b_th['max']}")
            if "max_increase" in b_th and ("max_increase" not in p_th or p_th["max_increase"] > b_th["max_increase"]):
                problems.append(f"metric {b_mid} max_increase loosened")
            if b_th.get("no_significant_drop") and not p_th.get("no_significant_drop"):
                problems.append(f"metric {b_mid} dropped no_significant_drop")

        for bs in base_spec.get("slices", []):
            s_name = bs["name"]
            ps = next((x for x in spec.get("slices", []) if x["name"] == s_name), None)
            if not ps:
                problems.append(f"slice {s_name} missing from spec")
                continue
            if bs.get("blocking") and not ps.get("blocking"):
                problems.append(f"slice {s_name} is no longer blocking")
            if "min" in bs and ("min" not in ps or ps["min"] < bs["min"]):
                problems.append(f"slice {s_name} min loosened")
            if bs.get("no_significant_drop") and not ps.get("no_significant_drop"):
                problems.append(f"slice {s_name} dropped no_significant_drop")

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices", []):
        name = s["name"]
        metric = s["metric"]
        blocking = s.get("blocking", True)
        slice_id = f"slice:{name}/{metric}"
        th = {k: v for k, v in s.items() if k in ("min", "no_significant_drop")}
        a = per_item(pr, metric, slice_name=name)
        verdict = "ok"
        note = ""
        val = None
        if not a:
            verdict = "missing"
        else:
            val = sum(a.values()) / len(a)
            if "min" in s and val < s["min"]:
                verdict = "fail"
            if s.get("no_significant_drop"):
                b = per_item(base, metric, slice_name=name)
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap(
                        [a[k] for k in keys],
                        [b[k] for k in keys],
                        n_resamples=bs.get("n_resamples", 1000),
                        rng=bs.get("rng", 2027),
                    )
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        verdict = "fail"
        if verdict != "ok" and blocking:
            blocked.append(slice_id)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if blocking else "warn")
        val_str = f"{round(val, 4):<8}" if val is not None else "None    "
        lines.append(f"  {slice_id:<22} {val_str} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
