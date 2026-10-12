"""Detector evaluation and calibration.

Usage
-----
    python -m evaluation.evaluate --manifest data/eval/manifest.csv --detector ml_image \
        --out evaluation/results/ml_image --target-fpr 0.01

The manifest is a CSV with columns:
    path,label[,<group columns>...]
where label is 1 for manipulated/synthetic and 0 for authentic. Any extra columns
(e.g. device, lighting, skin_tone, language, accent, generator, quality) are
treated as subgroup attributes. Per-subgroup error rates are reported so that
disparities are visible before a model is enabled.

Detectors:
    ml_image | ml_audio   -> evaluates the raw model score, writes calibration.json
    pipeline              -> evaluates the full ensemble classification (no calibration output)

Use an *independently sourced* dataset that was not used for training, and
include generators and capture conditions that the model never saw.
"""
import argparse
import csv
import json
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.detection.base import MediaContext  # noqa: E402
from app.detection.ensemble import assess  # noqa: E402
from app.detection.ml_model import AudioModelDetector, ImageModelDetector  # noqa: E402
from app.detection.registry import detectors_for  # noqa: E402
from app.detection.sniff import sniff  # noqa: E402


def roc_auc(y: np.ndarray, s: np.ndarray) -> float:
    pos, neg = s[y == 1], s[y == 0]
    if not len(pos) or not len(neg):
        return float("nan")
    order = np.argsort(np.concatenate([pos, neg]))
    ranks = np.empty(len(order))
    ranks[order] = np.arange(1, len(order) + 1)
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def rates(y: np.ndarray, pred: np.ndarray) -> dict:
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    return {"n": int(len(y)), "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "fpr": fp / (fp + tn) if fp + tn else None, "fnr": fn / (fn + tp) if fn + tp else None}


def threshold_at_fpr(y, s, target):
    neg = np.sort(s[y == 0])
    if not len(neg):
        return 0.5
    k = int(np.ceil((1 - target) * len(neg))) - 1
    return float(neg[min(max(k, 0), len(neg) - 1)]) + 1e-9


def threshold_at_fnr(y, s, target):
    pos = np.sort(s[y == 1])
    if not len(pos):
        return 0.5
    k = int(np.floor(target * len(pos)))
    return float(pos[min(k, len(pos) - 1)]) - 1e-9


def load(path: Path):
    data = path.read_bytes()
    sn = sniff(data[:64])
    if not sn or not sn.supported:
        raise ValueError(f"unsupported file {path}")
    out = Path(tempfile.mkdtemp())
    return MediaContext("eval", data, sn.kind, sn.mime, path, out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--detector", required=True, choices=["ml_image", "ml_audio", "pipeline"])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--target-fpr", type=float, default=0.01, help="FPR at the high-risk threshold")
    ap.add_argument("--target-fnr", type=float, default=0.05, help="FNR at the low (authentic) threshold")
    ap.add_argument("--input-size", type=int, default=224)
    args = ap.parse_args()

    rows = list(csv.DictReader(args.manifest.open(newline="", encoding="utf-8")))
    base = args.manifest.parent
    group_cols = [c for c in (rows[0].keys() if rows else []) if c not in ("path", "label")]
    det = {"ml_image": ImageModelDetector(), "ml_audio": AudioModelDetector()}.get(args.detector)
    if det:
        ok, why = det.availability()
        if not ok:
            sys.exit(f"Detector unavailable: {why}")

    ys, scores, preds, groups, errors = [], [], [], [], []
    for i, r in enumerate(rows):
        try:
            ctx = load(base / r["path"])
            if det:
                rep = det.run(ctx)
                raw = rep.facts.get("raw_score")
                if raw is None:
                    frames = rep.facts.get("frame_scores") or rep.facts.get("window_scores") or []
                    raw = max((f["score"] for f in frames), default=None)
                if raw is None:
                    raise ValueError(rep.reason or "no score")
                scores.append(float(raw))
            else:
                reps = [d.run(ctx) if d.availability()[0] else d.report("unavailable") for d in detectors_for(ctx.kind)]
                cls = assess(ctx.kind, reps)["classification"]
                preds.append(1 if cls in ("potentially_manipulated", "high_risk") else 0)
                scores.append({"likely_authentic": 0, "uncertain": 1, "potentially_manipulated": 2, "high_risk": 3}[cls])
            ys.append(int(r["label"]))
            groups.append({c: r.get(c, "") for c in group_cols})
        except Exception as e:
            errors.append({"path": r.get("path"), "error": str(e)})
        if (i + 1) % 50 == 0:
            print(f"{i + 1}/{len(rows)}", file=sys.stderr)

    y, s = np.array(ys), np.array(scores, dtype=float)
    args.out.mkdir(parents=True, exist_ok=True)
    report: dict = {"detector": args.detector, "manifest": str(args.manifest), "n": int(len(y)),
                    "positives": int(y.sum()), "errors": errors[:50], "error_count": len(errors),
                    "evaluated_at": datetime.now(timezone.utc).isoformat()}
    if det:
        hi = threshold_at_fpr(y, s, args.target_fpr)
        lo = min(threshold_at_fnr(y, s, args.target_fnr), hi)
        pred = (s >= hi).astype(int)
        report.update({"auc": roc_auc(y, s), "thresholds": {"low": lo, "high": hi}, "at_high": rates(y, pred),
                       "at_low": rates(y, (s > lo).astype(int))})
    else:
        pred = np.array(preds)
        report["flagged_vs_label"] = rates(y, pred)

    sub: dict = defaultdict(dict)
    for col in group_cols:
        vals = sorted({g[col] for g in groups if g[col]})
        for v in vals:
            m = np.array([g[col] == v for g in groups])
            sub[col][v] = rates(y[m], pred[m])
    report["subgroups"] = sub
    fprs = [r["fpr"] for col in sub.values() for r in col.values() if r["fpr"] is not None and r["n"] >= 30]
    if fprs:
        report["max_subgroup_fpr_gap"] = max(fprs) - min(fprs)

    (args.out / "report.json").write_text(json.dumps(report, indent=2))
    if det:
        calibration = {
            "calibrated": len(y) >= 500 and y.sum() >= 100 and (len(y) - y.sum()) >= 100,
            "low": report["thresholds"]["low"], "high": report["thresholds"]["high"],
            "input_size": args.input_size, "auc": report["auc"], "n": int(len(y)),
            "target_fpr": args.target_fpr, "target_fnr": args.target_fnr, "evaluated_at": report["evaluated_at"],
            "dataset": str(args.manifest),
        }
        if not calibration["calibrated"]:
            print("WARNING: dataset too small (need >=500 items, >=100 per class); calibration marked false.",
                  file=sys.stderr)
        (args.out / "calibration.json").write_text(json.dumps(calibration, indent=2))
    print(json.dumps({k: report[k] for k in report if k not in ("subgroups", "errors")}, indent=2))


if __name__ == "__main__":
    main()
