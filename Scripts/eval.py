#!/usr/bin/env python3
"""
JSON evaluation: compare ground-truth synthetic JSON to PDF extraction output.

Produces a scored report with per-field issue diagnostics suitable for
feeding back into extraction prompt tuning.

Dependencies:
  pip install deepdiff

Usage:
  python eval.py --gt ground_truth.json --pred prediction.json
  python eval.py --gt gt.json --pred pred.json --out report.json
  python eval.py --gt gt.json --pred pred.json --config eval_config.json

Public API:
  evaluate_extraction(ground_truth, prediction, config=None) -> dict
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from dataclasses import dataclass, asdict
from typing import Any

from deepdiff import DeepDiff


# ── Config ──────────────────────────────────────────────────────────────

DEFAULT_CONFIG: dict[str, Any] = {
    "normalization": {
        "strip_strings": True,
        "collapse_whitespace": True,
        "empty_is_null": True,
        "missing_is_null": True,
    },
    "diff": {
        "ignore_numeric_type_changes": True,
        "significant_digits": 2,
        "verbose_level": 2,
        "exclude_paths": [],
        "exclude_path_regexes": [],
    },
    "rubric": {
        "category_weights": {
            "structure": 0.45,
            "numbers": 0.40,
            "text": 0.15,
        },
        "penalties": {
            "structure": {"missing": 0.08, "extra": 0.04, "type": 0.06, "value": 0.03},
            "numbers":   {"missing": 0.08, "extra": 0.02, "type": 0.06, "value": 0.06},
            "text":      {"missing": 0.05, "extra": 0.02, "type": 0.03, "value": 0.04},
        },
        "category_caps": {
            "structure": 0.90,
            "numbers": 0.90,
            "text": 0.80,
        },
        "max_issues": 200,
        "severity_thresholds": {
            "high": 0.07,
            "med": 0.04,
            "low": 0.0,
        },
    },
}


# ── Issue ───────────────────────────────────────────────────────────────

@dataclass
class Issue:
    category: str   # structure | numbers | text
    kind: str       # missing | extra | type | value
    path: str
    expected: Any = None
    got: Any = None
    detail: str = ""
    penalty: float = 0.0
    severity: str = "low"


# ── Utilities ───────────────────────────────────────────────────────────

def _humanize_path(path: str) -> str:
    """root['sections'][0]['content'] → sections[0].content"""
    if not path.startswith("root"):
        return path
    p = path[4:]
    p = re.sub(r"\['([^']+)'\]", r".\1", p)
    return p.lstrip(".")


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _categorize(path: str, expected: Any, got: Any, kind: str) -> str:
    """Assign an issue to a scoring category based on the values involved."""
    if kind in ("missing", "extra"):
        if _is_number(expected) or _is_number(got):
            return "numbers"
        if isinstance(expected, str) or isinstance(got, str):
            return "text"
        return "structure"
    if _is_number(expected) or _is_number(got):
        return "numbers"
    if isinstance(expected, str) or isinstance(got, str):
        return "text"
    return "structure"


def _normalize(obj: Any, cfg: dict[str, Any]) -> Any:
    """Normalize whitespace; optionally treat empty strings as null."""
    strip = cfg.get("strip_strings", True)
    collapse = cfg.get("collapse_whitespace", True)
    empty_is_null = cfg.get("empty_is_null", True)

    def walk(x: Any) -> Any:
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        if isinstance(x, str):
            y = x.strip() if strip else x
            if collapse:
                y = re.sub(r"\s+", " ", y).strip()
            if empty_is_null and y == "":
                return None
            return y
        return x

    return walk(obj)


# ── Tree-view diff → Issues ────────────────────────────────────────────

def _diff_to_issues(
    dd: DeepDiff,
    rubric: dict[str, Any],
    diff_cfg: dict[str, Any] | None = None,
    missing_is_null: bool = True,
    _depth: int = 0,
) -> list[Issue]:
    """Walk DeepDiff tree-view result and emit one Issue per leaf difference.

    Container-level value changes (both sides are dict/list) are recursively
    decomposed into leaf-level issues via a sub-DeepDiff.
    """
    MAX_DECOMPOSE_DEPTH = 4
    penalties_cfg = rubric["penalties"]
    thresholds = rubric["severity_thresholds"]
    issues: list[Issue] = []

    def _penalty(cat: str, kind: str) -> float:
        cat_tbl = penalties_cfg.get(cat, penalties_cfg.get("text", {}))
        return float(cat_tbl.get(kind, 0.03))

    def _severity(p: float) -> str:
        if p >= thresholds.get("high", 0.07):
            return "high"
        if p >= thresholds.get("med", 0.04):
            return "med"
        return "low"

    def emit(kind: str, path: str, exp: Any, got: Any, detail: str = ""):
        cat = _categorize(path, exp, got, kind)
        pen = _penalty(cat, kind)
        issues.append(Issue(cat, kind, path, exp, got, detail, pen, _severity(pen)))

    for item in dd.get("values_changed", []):
        path = _humanize_path(item.path())
        if (
            isinstance(item.t1, (dict, list))
            and isinstance(item.t2, (dict, list))
            and _depth < MAX_DECOMPOSE_DEPTH
        ):
            sub_dd = DeepDiff(
                item.t1, item.t2,
                view="tree",
                ignore_numeric_type_changes=(
                    diff_cfg.get("ignore_numeric_type_changes", True) if diff_cfg else True
                ),
                significant_digits=diff_cfg.get("significant_digits", 2) if diff_cfg else 2,
                verbose_level=2,
            )
            sub_issues = _diff_to_issues(
                sub_dd, rubric, diff_cfg, missing_is_null, _depth + 1,
            )
            for si in sub_issues:
                si.path = f"{path}.{si.path}" if si.path else path
            if sub_issues:
                issues.extend(sub_issues)
                continue
        emit("value", path, item.t1, item.t2)

    for item in dd.get("type_changes", []):
        detail = f"{type(item.t1).__name__} \u2192 {type(item.t2).__name__}"
        emit("type", _humanize_path(item.path()), item.t1, item.t2, detail)

    for item in dd.get("dictionary_item_removed", []):
        if missing_is_null and item.t1 is None:
            continue
        emit("missing", _humanize_path(item.path()), item.t1, None, "missing key")

    for item in dd.get("dictionary_item_added", []):
        if missing_is_null and item.t2 is None:
            continue
        emit("extra", _humanize_path(item.path()), None, item.t2, "extra key")

    for item in dd.get("iterable_item_removed", []):
        emit("missing", _humanize_path(item.path()), item.t1, None, "missing list item")

    for item in dd.get("iterable_item_added", []):
        emit("extra", _humanize_path(item.path()), None, item.t2, "extra list item")

    return issues


# ── Scoring ─────────────────────────────────────────────────────────────

def _score(issues: list[Issue], rubric: dict[str, Any]) -> dict[str, Any]:
    """Compute weighted category subscores and an aggregate score."""
    caps = rubric["category_caps"]
    weights = rubric["category_weights"]

    raw: dict[str, float] = {}
    for it in issues:
        raw[it.category] = raw.get(it.category, 0.0) + it.penalty

    capped = {cat: min(p, caps.get(cat, 0.9)) for cat, p in raw.items()}

    subscores = {cat: 1.0 for cat in weights}
    for cat, p in capped.items():
        subscores[cat] = max(0.0, 1.0 - p)

    total_w = sum(weights.values())
    score = sum(weights.get(c, 0) * subscores.get(c, 1.0) for c in weights) / total_w

    return {
        "score": round(max(0.0, min(1.0, score)), 4),
        "subscores": subscores,
        "category_penalties": capped,
    }


# ── Exclusion filter ───────────────────────────────────────────────────

def _apply_exclusions(issues: list[Issue], diff_cfg: dict[str, Any]) -> list[Issue]:
    regexes = [re.compile(r) for r in diff_cfg.get("exclude_path_regexes", []) if r]
    if not regexes:
        return issues
    return [it for it in issues if not any(r.search(it.path) for r in regexes)]


# ── Public API ──────────────────────────────────────────────────────────

def evaluate_extraction(
    ground_truth: dict[str, Any],
    prediction: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Compare extracted JSON to ground truth.

    Returns a report with:
      score      – aggregate 0‒1 quality score
      subscores  – per-category (structure, numbers, text)
      issues     – ranked list of individual discrepancies
    """
    cfg = deepcopy(DEFAULT_CONFIG)
    if config:
        for k, v in config.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v

    rubric = cfg["rubric"]
    diff_cfg = cfg["diff"]

    norm_cfg = cfg["normalization"]
    missing_is_null = norm_cfg.get("missing_is_null", True)

    gt = _normalize(ground_truth, norm_cfg)
    pred = _normalize(prediction, norm_cfg)

    dd = DeepDiff(
        gt,
        pred,
        view="tree",
        ignore_numeric_type_changes=diff_cfg["ignore_numeric_type_changes"],
        significant_digits=diff_cfg["significant_digits"],
        verbose_level=diff_cfg["verbose_level"],
        exclude_paths=diff_cfg.get("exclude_paths", []),
    )

    issues = _diff_to_issues(dd, rubric, diff_cfg, missing_is_null)
    issues = _apply_exclusions(issues, diff_cfg)

    scoring = _score(issues, rubric)

    issues.sort(key=lambda x: (-x.penalty, x.category, x.path))
    max_issues = rubric.get("max_issues", 200)

    by_cat: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for it in issues:
        by_cat[it.category] = by_cat.get(it.category, 0) + 1
        by_kind[it.kind] = by_kind.get(it.kind, 0) + 1

    return {
        **scoring,
        "counts_by_category": by_cat,
        "counts_by_kind": by_kind,
        "issues": [asdict(i) for i in issues[:max_issues]],
    }


# ── CLI ─────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Evaluate extracted JSON vs ground truth with scored feedback.",
    )
    ap.add_argument("--gt", required=True, help="Path to ground-truth JSON.")
    ap.add_argument("--pred", required=True, help="Path to predicted/extracted JSON.")
    ap.add_argument("--config", default=None, help="Optional config JSON to merge into defaults.")
    ap.add_argument("--out", default=None, help="Write report to path (else stdout).")
    args = ap.parse_args(argv)

    with open(args.gt) as f:
        gt = json.load(f)
    with open(args.pred) as f:
        pred = json.load(f)

    cfg = None
    if args.config:
        with open(args.config) as f:
            cfg = json.load(f)

    report = evaluate_extraction(gt, pred, cfg)

    out = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    if args.out:
        with open(args.out, "w") as f:
            f.write(out)
    else:
        print(out)

    if report["score"] < 0.25:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
