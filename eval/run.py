"""Scan the corpus, score per-class recall + localization, and the clean-set
false-positive rate. Writes eval/results.json and prints the table.

Recall counts a case as found when some finding shares its class and page and
(where the injection has a box) overlaps it. Localization is the median IoU of
those matches. The false-positive rate is the fraction of clean controls that
produced any high-severity structural finding -- the number that must stay zero.
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from verso.detect import IMPLEMENTED_CLASSES
from verso.models import BBox
from verso.scan import scan

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "corpus" / "build"
LABELS = BUILD / "labels.json"
RESULTS = ROOT / "eval" / "results.json"

ALL_CLASSES = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10"]
FOUND_IOU = 0.25          # overlap needed to count a located case as found


def _iou(a: list[float], b: BBox) -> float:
    return BBox(a[0], a[1], a[2], a[3]).iou(b)


def _match(case: dict, findings) -> tuple[bool, float | None]:
    cls, page = case["attack_class"], case["page"]
    cands = [f for f in findings if f.attack_class == cls and f.page == page]
    if not cands:
        return False, None
    if case["bbox"] is None:
        return True, None
    best = 0.0
    for f in cands:
        if f.bbox is not None:
            best = max(best, _iou(case["bbox"], f.bbox))
    return best >= FOUND_IOU, best


def evaluate() -> dict:
    labels = json.loads(LABELS.read_text())
    t0 = time.time()
    n_pages = 0

    per_class: dict[str, dict] = {}
    for case in labels["attacks"]:
        r = scan(BUILD / case["file"])
        n_pages += r.n_pages
        found, iou = _match(case, r.findings)
        bucket = per_class.setdefault(case["attack_class"],
                                      {"cases": 0, "found": 0, "ious": []})
        bucket["cases"] += 1
        bucket["found"] += 1 if found else 0
        if iou is not None:
            bucket["ious"].append(iou)

    class_rows = {}
    for cls, b in sorted(per_class.items()):
        recall = b["found"] / b["cases"] if b["cases"] else 0.0
        med = statistics.median(b["ious"]) if b["ious"] else None
        class_rows[cls] = {
            "cases": b["cases"], "found": b["found"],
            "recall": round(recall, 3),
            "median_iou": round(med, 3) if med is not None else None,
        }

    # clean controls
    fp_files = []
    for c in labels["clean"]:
        r = scan(BUILD / c["file"])
        n_pages += r.n_pages
        if r.high_findings:
            fp_files.append({
                "id": c["id"],
                "rules": sorted({f.rule for f in r.high_findings}),
            })
    n_clean = len(labels["clean"])
    fp_rate = len(fp_files) / n_clean if n_clean else 0.0

    elapsed = time.time() - t0
    return {
        "per_class": class_rows,
        "clean": {
            "count": n_clean,
            "false_positives": len(fp_files),
            "fp_rate": round(fp_rate, 3),
            "fp_files": fp_files,
        },
        "implemented": IMPLEMENTED_CLASSES,
        "not_implemented": [c for c in ALL_CLASSES if c not in IMPLEMENTED_CLASSES],
        "wall_clock_s": round(elapsed, 1),
        "pages_scanned": n_pages,
        "ms_per_page": round(1000 * elapsed / n_pages, 1) if n_pages else None,
    }


def print_table(res: dict) -> None:
    print()
    print("class  cases  found  recall   median IoU")
    for cls in ALL_CLASSES:
        if cls in res["per_class"]:
            row = res["per_class"][cls]
            miou = row["median_iou"]
            miou_s = f"{miou:.2f}" if miou is not None else " n/a"
            print(f"{cls:<5} {row['cases']:>6} {row['found']:>6} "
                  f"{row['recall']:>7.3f}   {miou_s:>10}")
        elif cls in res["not_implemented"]:
            print(f"{cls:<5} {'--':>6} {'--':>6} {'not impl.':>9}")
    print("-" * 43)
    clean = res["clean"]
    print(f"clean {clean['count']:>6} {clean['false_positives']:>6}   "
          f"FP rate {clean['fp_rate']:.3f}")
    if clean["fp_files"]:
        for fp in clean["fp_files"]:
            print(f"        ! {fp['id']}: {', '.join(fp['rules'])}")
    if "determinism" in res:
        print(f"determinism: {res['determinism']}")
    print(f"\n{res['pages_scanned']} pages in {res['wall_clock_s']}s "
          f"({res['ms_per_page']} ms/page)")


def main() -> None:
    res = evaluate()
    RESULTS.write_text(json.dumps(res, indent=2, sort_keys=True))
    print_table(res)


if __name__ == "__main__":
    main()
