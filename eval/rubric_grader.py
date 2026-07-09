"""
rubric_grader.py — LLM-as-judge that scores each reply on 4 dimensions.

Run:
    python eval/rubric_grader.py

Input:  results/replies.jsonl
Output: results/scores.jsonl

Each output record:
{
    "ticket_id": "ticket_001",
    "category": "...",
    "is_adversarial": false,
    "adversarial_type": null,
    "skipped": false,          -- true for abstained replies
    "scores": {
        "factual_grounding": 4,      -- 1-5: did it stick to the policy?
        "tone_match": 5,             -- 1-5: did tone fit the customer mood?
        "resolution_completeness": 3,-- 1-5: did it actually resolve the issue?
        "conciseness": 4             -- 1-5: was it appropriately brief?
    },
    "composite": 4.0,               -- average of the 4 sub-scores
    "failure_mode": null            -- populated ONLY when composite < 3.0
}

Design notes:
- Uses gemini-3.1-pro-preview (strongest model) for better judgment quality.
- Failure mode taxonomy is fixed; grader must choose from it (no free-form).
- Abstained tickets are skipped (correct behavior — nothing was sent).
"""

import json
import os
import re
import sys
import time

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
import google.generativeai as genai
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

MODEL = os.getenv("GRADER_MODEL", "gemini-3.1-flash-lite")

GRADER_PROMPT = """
You are an expert quality evaluator for customer support replies.
Your job is to score the AI-generated reply below on 4 dimensions.

--- ORIGINAL CUSTOMER EMAIL ---
Category: {category}
Mood: {mood}
{customer_msg}
--- END EMAIL ---

--- AI-GENERATED REPLY ---
{reply_text}
--- END REPLY ---

Score the reply on each dimension from 1 (very poor) to 5 (excellent):

1. **factual_grounding** (1-5): Does the reply stick to verifiable facts? Does it avoid inventing policy details, refund amounts, timelines, or promises not grounded in standard policy for this category? 
   - 5 = every claim is policy-grounded; 1 = invents fictional policies or facts.

2. **tone_match** (1-5): Does the tone match the customer's mood?
   - Angry/frustrated customers need empathy-first, patient tone.
   - Neutral/polite customers need friendly, efficient tone.
   - 5 = perfect tone fit; 1 = completely mismatched (e.g., curt reply to upset customer).

3. **resolution_completeness** (1-5): Does the reply actually address and attempt to resolve the core issue the customer raised?
   - 5 = fully resolves or gives a clear next step; 1 = ignores the question entirely.

4. **conciseness** (1-5): Is the reply appropriately brief without being terse?
   - 5 = covers everything needed with no padding; 1 = buries the answer in walls of text.

IMPORTANT: If the composite average score is below 3.0, you MUST also identify the primary failure_mode from this fixed list:
- "hallucinated_policy" — invented a refund/policy detail not in standard support knowledge
- "wrong_tone" — mismatched to customer mood
- "ignored_question" — didn't address what was actually asked
- "too_long" — verbose, buries the answer
- "other:<brief note>" — use this only if none of the above fit

Return ONLY a valid JSON object (no markdown, no extra text):
{{
  "scores": {{
    "factual_grounding": <1-5>,
    "tone_match": <1-5>,
    "resolution_completeness": <1-5>,
    "conciseness": <1-5>
  }},
  "composite": <average of the 4 scores, 1 decimal place>,
  "failure_mode": null | "<one of the tags above>"
}}
""".strip()


def call_gemini(prompt: str, retries: int = 3) -> str:
    model = genai.GenerativeModel(MODEL)
    for attempt in range(retries):
        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=512,
                ),
            )
            return response.text
        except Exception as exc:
            if attempt < retries - 1:
                wait = 2 ** attempt
                time.sleep(wait)
            else:
                raise


def parse_score_json(text: str) -> dict:
    """Parse and validate grader JSON output."""
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found: {text[:200]}")
    obj = json.loads(text[start : end + 1])

    scores = obj.get("scores", {})
    dims = ["factual_grounding", "tone_match", "resolution_completeness", "conciseness"]
    for dim in dims:
        if dim not in scores:
            raise ValueError(f"Missing score dimension '{dim}'")
        scores[dim] = max(1, min(5, int(scores[dim])))

    # Recompute composite to ensure consistency
    composite = round(sum(scores[d] for d in dims) / 4, 1)
    obj["composite"] = composite

    # Validate failure_mode
    if composite < 3.0 and (not obj.get("failure_mode") or obj["failure_mode"] == "null"):
        obj["failure_mode"] = "other:unspecified"
    elif composite >= 3.0:
        obj["failure_mode"] = None

    return obj


def grade_reply(reply: dict) -> dict:
    """Grade a single reply."""
    prompt = GRADER_PROMPT.format(
        category=reply["category"],
        mood=reply.get("mood", "neutral"),
        customer_msg=reply["customer_msg"],
        reply_text=reply["reply_text"],
    )
    raw = call_gemini(prompt)
    graded = parse_score_json(raw)
    return {
        "ticket_id": reply["ticket_id"],
        "category": reply["category"],
        "is_adversarial": reply.get("is_adversarial", False),
        "adversarial_type": reply.get("adversarial_type"),
        "skipped": False,
        **graded,
    }


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    replies_path = os.path.join(base_dir, "results", "replies.jsonl")
    output_path = os.path.join(base_dir, "results", "scores.jsonl")

    if not os.path.exists(replies_path):
        print(f"ERROR: {replies_path} not found. Run generator/generate_replies.py first.")
        sys.exit(1)

    # Load replies
    replies = []
    with open(replies_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                replies.append(json.loads(line))

    print("=" * 60)
    print(f"Rubric Grader — {len(replies)} replies, model: {MODEL}")
    print("=" * 60)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    results = []
    errors = []

    with open(output_path, "w", encoding="utf-8") as out_f:
        for reply in tqdm(replies, desc="Grading replies"):
            ticket_id = reply["ticket_id"]
            # Skip abstained replies — nothing was sent, nothing to grade
            if reply.get("abstain", False):
                skipped_record = {
                    "ticket_id": ticket_id,
                    "category": reply["category"],
                    "is_adversarial": reply.get("is_adversarial", False),
                    "adversarial_type": reply.get("adversarial_type"),
                    "skipped": True,
                    "scores": None,
                    "composite": None,
                    "failure_mode": None,
                }
                results.append(skipped_record)
                out_f.write(json.dumps(skipped_record) + "\n")
                continue

            try:
                scored = grade_reply(reply)
                results.append(scored)
                out_f.write(json.dumps(scored) + "\n")
                out_f.flush()
            except Exception as exc:
                print(f"\n  [ERROR] {ticket_id}: {exc}")
                errors.append(ticket_id)
            time.sleep(0.5)

    # Summary stats
    graded = [r for r in results if not r["skipped"]]
    skipped = [r for r in results if r["skipped"]]
    low_scoring = [r for r in graded if r["composite"] is not None and r["composite"] < 3.0]
    adv_graded = [r for r in graded if r["is_adversarial"]]
    normal_graded = [r for r in graded if not r["is_adversarial"]]

    def avg_composite(lst):
        vals = [r["composite"] for r in lst if r["composite"] is not None]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    failure_modes = {}
    for r in graded:
        fm = r.get("failure_mode")
        if fm:
            failure_modes[fm] = failure_modes.get(fm, 0) + 1

    print(f"\n{'='*60}")
    print(f"Done. {len(results)} records written to {output_path}")
    print(f"  Graded:        {len(graded)}")
    print(f"  Skipped:       {len(skipped)} (abstained)")
    print(f"  Avg composite: {avg_composite(graded)}")
    print(f"  Normal avg:    {avg_composite(normal_graded)}")
    print(f"  Adversarial avg:{avg_composite(adv_graded)}")
    print(f"  Low scoring (<3.0): {len(low_scoring)}")
    if failure_modes:
        print(f"  Failure modes: {failure_modes}")
    if errors:
        print(f"  Errors ({len(errors)}): {errors}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
