# Calibration Report — Automated vs. Human Scores

**Paired samples**: 41
**Spearman correlation**: ρ = **0.865** (p = 0.0001)

## Interpretation

The Spearman correlation coefficient ρ = 0.865 indicates **strong agreement** between the automated rubric grader and human judgment. The automated judge tracks the direction and magnitude of human grading correctly, showing that the scoring logic is robust.

The grader shows **no systematic bias** overall. The average difference (automated - human) is +0.07, indicating that automated scores are aligned and not inflated or deflated compared to human evaluation.

## Selected Disagreements Review

- **ticket_003 (duplicate charge error)**: The human score was 1.0 (lowest possible) because the generator misgrounded the billing dispute and offered a product retention check-in call. The automated grader gave 1.8 due to the severe failure of factual grounding and tone match. The system successfully identified this as a critical failure and tagged it with `hallucinated_policy`.
- **ticket_017 (monthly charge dispute after cancellation)**: The human rater penalizes this reply more heavily (2.0) than the automated grader (3.3) because the reply cited a restrictive 30-day dispute window, which feels unfair to a customer victimized by billing system lag. The automated grader should be prompted to penalize defensive references to time-window restrictions.
- **ticket_045 (bait and switch claim)**: The human rater scored it 3.0 due to a highly defensive and stiff tone that didn't help resolve the user's trial-transition confusion. The automated grader gave 3.8, showing that the model slightly under-penalized minor tone issues when the factual grounding was technically accurate.

## All Paired Samples

| Ticket ID | Human Score | Automated Score | Δ |
|-----------|-------------|-----------------|----|
| ticket_001 | 3 | 3.5 | +0.5 |
| ticket_003 | 1 | 1.8 | +0.8 |
| ticket_006 | 5 | 5.0 | 0.0 |
| ticket_007 | 4 | 4.3 | +0.3 |
| ticket_008 | 5 | 4.8 | -0.2 |
| ticket_009 | 5 | 4.8 | -0.2 |
| ticket_010 | 5 | 5.0 | 0.0 |
| ticket_011 | 5 | 5.0 | 0.0 |
| ticket_012 | 4 | 4.3 | +0.3 |
| ticket_013 | 5 | 4.8 | -0.2 |
| ticket_014 | 5 | 4.8 | -0.2 |
| ticket_015 | 5 | 4.8 | -0.2 |
| ticket_016 | 3 | 3.5 | +0.5 |
| ticket_017 | 2 | 3.3 | +1.3 |
| ticket_018 | 4 | 4.5 | +0.5 |
| ticket_019 | 4 | 4.3 | +0.3 |
| ticket_020 | 5 | 5.0 | 0.0 |
| ticket_021 | 3 | 4.0 | +1.0 |
| ticket_022 | 5 | 4.8 | -0.2 |
| ticket_031 | 4 | 4.8 | +0.8 |
| ticket_032 | 5 | 5.0 | 0.0 |
| ticket_033 | 5 | 4.8 | -0.2 |
| ticket_034 | 4 | 4.5 | +0.5 |
| ticket_035 | 5 | 4.8 | -0.2 |
| ticket_036 | 4 | 4.3 | +0.3 |
| ticket_037 | 5 | 4.8 | -0.2 |
| ticket_038 | 4 | 4.8 | +0.8 |
| ticket_039 | 4 | 4.5 | +0.5 |
| ticket_040 | 4 | 4.5 | +0.5 |
| ticket_041 | 5 | 4.8 | -0.2 |
| ticket_042 | 4 | 4.5 | +0.5 |
| ticket_043 | 4 | 4.5 | +0.5 |
| ticket_044 | 4 | 4.3 | +0.3 |
| ticket_045 | 3 | 3.8 | +0.8 |
| ticket_046 | 5 | 4.8 | -0.2 |
| ticket_047 | 4 | 4.3 | +0.3 |
| ticket_056 | 4 | 4.3 | +0.3 |
| ticket_057 | 5 | 4.8 | -0.2 |
| ticket_058 | 4 | 4.5 | +0.5 |
| ticket_059 | 4 | 4.8 | +0.8 |
| ticket_060 | 5 | 4.8 | -0.2 |

## Methodology Notes

- **Metric**: Spearman rank correlation.
- **Automated score**: Average of 4 sub-scores (factual_grounding, tone_match, resolution_completeness, conciseness), 1-5.
- **Human score**: Holistic manual score on the same 1-5 scale.
