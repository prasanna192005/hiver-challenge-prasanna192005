"""
calibration.py — Correlates automated rubric scores against hand-labeled gold set.

Run:
    python eval/calibration.py

Input:
    gold/gold.jsonl       — hand-labeled replies with human_score (1-5)
    results/scores.jsonl  — automated scores from rubric_grader.py

Output:
    results/calibration_report.md

Design notes:
- Uses Spearman rank correlation (robust to outliers, doesn't assume normality).
- Flags the top disagreements (|automated - human| >= 1.5 points).
- Gives an honest interpretation of what the correlation means.
- If gold.jsonl has human_score = null for an entry, that entry is skipped.
"""

import json
import os
import sys

from scipy.stats import spearmanr
from dotenv import load_dotenv

load_dotenv()


def load_jsonl(path: str) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gold_path = os.path.join(base_dir, "gold", "gold.jsonl")
    scores_path = os.path.join(base_dir, "results", "scores.jsonl")
    output_path = os.path.join(base_dir, "results", "calibration_report.md")

    if not os.path.exists(gold_path):
        print(f"ERROR: {gold_path} not found. Create the gold set first.")
        sys.exit(1)
    if not os.path.exists(scores_path):
        print(f"ERROR: {scores_path} not found. Run eval/rubric_grader.py first.")
        sys.exit(1)

    gold_records = load_jsonl(gold_path)
    scores_records = load_jsonl(scores_path)

    # Build lookup: ticket_id -> automated composite
    auto_scores = {
        r["ticket_id"]: r["composite"]
        for r in scores_records
        if not r.get("skipped") and r.get("composite") is not None
    }

    # Build paired list (skip if human_score is null or ticket not in auto_scores)
    pairs = []
    for g in gold_records:
        tid = g.get("ticket_id")
        human_score = g.get("human_score")
        if human_score is None or tid not in auto_scores:
            continue
        auto = auto_scores[tid]
        pairs.append({
            "ticket_id": tid,
            "human_score": float(human_score),
            "automated_score": float(auto),
            "delta": round(float(auto) - float(human_score), 2),
        })

    if len(pairs) < 5:
        print(
            f"WARNING: Only {len(pairs)} valid paired samples found. "
            "Need at least 5 for meaningful correlation. "
            "Fill in more human_score values in gold/gold.jsonl."
        )
        if len(pairs) == 0:
            # Write a placeholder report
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("# Calibration Report\n\n")
                f.write("**Status**: No human-labeled gold set entries found.\n\n")
                f.write(
                    "To run calibration: open `gold/gold.jsonl`, fill in `human_score` "
                    "values (1–5 integers), then re-run `python eval/calibration.py`.\n"
                )
            print(f"Placeholder report written to {output_path}")
            return

    human_scores = [p["human_score"] for p in pairs]
    auto_scores_list = [p["automated_score"] for p in pairs]

    corr, pvalue = spearmanr(human_scores, auto_scores_list)

    # Top disagreements
    disagreements = sorted(pairs, key=lambda x: abs(x["delta"]), reverse=True)
    big_disagreements = [d for d in disagreements if abs(d["delta"]) >= 1.5]

    # Interpretation
    if corr >= 0.8:
        interpretation = (
            "Strong agreement — the automated grader tracks human judgment well. "
            "Safe to use automated scores as a proxy for human evaluation."
        )
    elif corr >= 0.6:
        interpretation = (
            "Moderate agreement — the grader is directionally correct but shows "
            "some systematic biases. Review top disagreements before trusting the grader fully."
        )
    elif corr >= 0.4:
        interpretation = (
            "Weak agreement — the automated grader diverges meaningfully from human "
            "raters. Specific failure modes (e.g., verbosity) may not be penalized appropriately."
        )
    else:
        interpretation = (
            "Poor agreement — the automated grader does not reliably track human "
            "judgment. Results should be treated with caution; consider revising the grading prompt."
        )

    # Bias direction
    avg_delta = sum(p["delta"] for p in pairs) / len(pairs)
    if avg_delta > 0.3:
        bias_note = "The grader tends to **over-score** compared to human raters (inflated scores)."
    elif avg_delta < -0.3:
        bias_note = "The grader tends to **under-score** compared to human raters (deflated scores)."
    else:
        bias_note = "The grader shows **no systematic bias** — average delta is near zero."

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Calibration Report — Automated vs. Human Scores\n\n")
        f.write(f"**Paired samples**: {len(pairs)}\n")
        f.write(f"**Spearman correlation**: ρ = **{corr:.3f}** (p = {pvalue:.4f})\n\n")

        f.write("## Interpretation\n\n")
        f.write(f"{interpretation}\n\n")
        f.write(f"{bias_note}\n\n")

        if big_disagreements:
            f.write("## Biggest Disagreements (|Δ| ≥ 1.5)\n\n")
            f.write("| Ticket ID | Human Score | Automated Score | Δ |\n")
            f.write("|-----------|-------------|-----------------|----|\n")
            for d in big_disagreements[:10]:
                f.write(
                    f"| {d['ticket_id']} | {d['human_score']} "
                    f"| {d['automated_score']} | {d['delta']:+.1f} |\n"
                )
            f.write("\n")

        f.write("## All Paired Samples\n\n")
        f.write("| Ticket ID | Human Score | Automated Score | Δ |\n")
        f.write("|-----------|-------------|-----------------|----|\n")
        for p in sorted(pairs, key=lambda x: x["ticket_id"]):
            f.write(
                f"| {p['ticket_id']} | {p['human_score']} "
                f"| {p['automated_score']} | {p['delta']:+.1f} |\n"
            )
        f.write("\n")

        f.write("## Methodology Notes\n\n")
        f.write(
            "- **Metric**: Spearman rank correlation (non-parametric, robust to outliers).\n"
            "- **Automated score**: average of 4 sub-scores "
            "(factual_grounding, tone_match, resolution_completeness, conciseness), each 1–5.\n"
            "- **Human score**: direct holistic judgment on the same 1–5 scale.\n"
            "- **Gold set construction**: replies were selected to cover a mix of normal and "
            "adversarial tickets, and a range of automated scores.\n"
        )

    print(f"\nCalibration report written to {output_path}")
    print(f"  Spearman ρ = {corr:.3f} (p = {pvalue:.4f})")
    print(f"  {interpretation}")


if __name__ == "__main__":
    main()
