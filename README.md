# Hiver Open Challenge — AI Email Reply Generator + Evaluation System

A production-grade pipeline that generates AI support replies, evaluates them with a two-layer system (rubric grader + adversarial customer simulator), and calibrates the evaluator against human judgment.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your API key
cp .env.example .env
# Edit .env and set GOOGLE_API_KEY=<your key>

# 3. Run the full pipeline
python run_all.py
```

Open `results/report.html` in your browser.

---

## What Gets Built

```
python run_all.py
├── data/generate_dataset.py    → data/tickets.jsonl       (60 tickets, 10 adversarial)
├── generator/generate_replies.py → results/replies.jsonl  (replies + confidence + abstain)
├── eval/rubric_grader.py       → results/scores.jsonl     (4-dim scores + failure mode tags)
├── eval/customer_simulator.py  → results/simulation.jsonl (resolved? turns? repeated?)
├── [inline]                    → results/report.html       (full dashboard)
└── eval/calibration.py         → results/calibration_report.md (Spearman ρ vs. human)
```

---

## Partial Runs

```bash
python run_all.py --skip-dataset    # use existing tickets.jsonl, re-run everything else
python run_all.py --skip-replies    # skip dataset + replies, re-run grader/simulator/report
python run_all.py --report-only     # just regenerate the HTML from existing result files
python eval/calibration.py          # run calibration standalone after filling gold/gold.jsonl
```

---

## Architecture

### Grounding Strategy: Category Lookup, Not Embeddings

Each ticket is tagged with a category (`billing`, `shipping`, `refund`, `bug`, `churn-risk`) at generation time. The generator looks up the matching policy snippet from `data/policy_snippets.py` — a simple dict, O(1) access.

**Why not RAG/embeddings?**
With 5 categories and stable, curated policy text, vector search would add 200–500ms of latency per call, require an embedding model, and introduce retrieval errors — all with zero accuracy benefit. Every ticket gets *exactly* the right policy context every time. This is the right tradeoff at this scale.

### Why This Evaluation Setup is Trustworthy

A single LLM-judge score is not trustworthy on its own — it has no anchor to reality. This system uses three complementary layers:

| Layer | What it measures | Why it matters |
|-------|-----------------|----------------|
| **Rubric Grader** | Quality of the reply itself (4 dimensions) | Catches factual hallucinations, tone mismatches, incomplete answers |
| **Customer Simulator** | Does the reply *actually resolve the issue*? | Outcome-based signal — catches replies that look good but don't work |
| **Calibration** | Does the automated score track human judgment? | Makes the evaluator self-aware of its own biases |

No single score tells the whole story. A reply can score 4/5 on rubric but fail simulation if it's technically correct but doesn't actually close the loop. The simulator catches that.

### Models

| Step | Model | Reasoning |
|------|-------|-----------|
| Dataset generation | `gemini-3.5-flash` | High throughput, creative synthesis |
| Reply generation | `gemini-3.5-flash` | Fast, policy-grounded structured output |
| Rubric grading | `gemini-3.1-pro-preview` | Best judgment quality for LLM-as-judge |
| Customer simulation | `gemini-3.5-flash` | Fast enough for 2-3 turn conversations |

---

## Adversarial Tickets + Abstention: Robustness, Not Just Average Quality

An eval system that only measures happy-path tickets doesn't tell you how the AI behaves in production. This system includes 10 adversarial tickets (≈15% of the dataset) across 4 sub-types:

| Sub-type | What it tests |
|----------|--------------|
| `false_claim` | Does the AI push back on incorrect customer assertions? |
| `hostile_tone` | Does the AI maintain empathy when the customer is aggressive? |
| `broken_english` | Does the AI charitably interpret garbled requests? |
| `policy_violation_request` | Does the AI politely refuse impossible requests instead of hallucinating a workaround? |

### Key robustness signals in the report:

**Adversarial vs. Normal score gap**: If the AI handles adversarial tickets nearly as well as normal ones, that's strong evidence of robustness. If there's a large gap, the failure mode table shows *why*.

**Abstention rate on `policy_violation_request`**: The AI should abstain (flag for human review) on most policy-violating requests, because there's no policy-compliant resolution. A near-zero abstention rate on these tickets would be a red flag — it means the AI is likely hallucinating workarounds. Target: ≥70% abstention on `policy_violation_request`, ≤5% on normal tickets.

This ratio is itself a quality signal that a bare accuracy score would never surface.

---

## Output Files

| File | Contents |
|------|---------|
| `results/replies.jsonl` | `{ticket_id, reply_text, confidence, abstain, abstain_reason, ...}` |
| `results/scores.jsonl` | `{ticket_id, scores:{fg,tm,rc,co}, composite, failure_mode}` |
| `results/simulation.jsonl` | `{ticket_id, outcome, turns_to_resolve, had_to_repeat_ask, conversation}` |
| `results/report.html` | Full sortable/filterable dashboard — open in browser |
| `results/calibration_report.md` | Spearman ρ + disagreement table + interpretation |

---

## Calibration: Filling the Gold Set

After the first run, open `results/replies.jsonl` and score 25 replies on a 1–5 scale:
- **5**: Excellent — correct, empathetic, fully resolves the issue, appropriately brief
- **4**: Good — minor issues but gets the job done
- **3**: Passable — addresses the issue but has meaningful flaws
- **2**: Poor — significant problems (wrong info, bad tone, incomplete)
- **1**: Fails — should never be sent

Update `gold/gold.jsonl` with your scores:
```jsonl
{"ticket_id": "ticket_001", "human_score": 4, "notes": "Good tone, slight verbosity"}
{"ticket_id": "ticket_007", "human_score": 2, "notes": "Ignored the refund question"}
```

Then run:
```bash
python eval/calibration.py
```

A Spearman ρ ≥ 0.7 means the automated grader is reliable. Below 0.5 means the grading prompt needs revision.

---

## Schema Reference

### tickets.jsonl
```json
{
  "id": "ticket_001",
  "category": "billing | shipping | refund | bug | churn-risk",
  "customer_msg": "...",
  "mood": "neutral | frustrated | angry | confused | polite",
  "is_adversarial": false,
  "adversarial_type": null
}
```

### replies.jsonl
```json
{
  "ticket_id": "ticket_001",
  "reply_text": "...",
  "confidence": "high | medium | low",
  "abstain": false,
  "abstain_reason": null
}
```

### scores.jsonl
```json
{
  "ticket_id": "ticket_001",
  "scores": {"factual_grounding": 4, "tone_match": 5, "resolution_completeness": 4, "conciseness": 3},
  "composite": 4.0,
  "failure_mode": null
}
```

### simulation.jsonl
```json
{
  "ticket_id": "ticket_001",
  "outcome": "resolved | partially_resolved | not_resolved",
  "turns_to_resolve": 1,
  "had_to_repeat_ask": false,
  "conversation": [{"role": "support", "text": "..."}, {"role": "customer", "text": "..."}]
}
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_API_KEY` | required | Your Google AI Studio API key |
| `GENERATOR_MODEL` | `gemini-3.5-flash` | Model for reply generation |
| `GRADER_MODEL` | `gemini-3.1-pro-preview` | Model for rubric grading |
| `SIMULATOR_MODEL` | `gemini-3.5-flash` | Model for customer simulation |
| `DATASET_MODEL` | `gemini-3.5-flash` | Model for dataset generation |
