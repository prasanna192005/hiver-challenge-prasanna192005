"""
generate_replies.py — Generates AI support replies for all tickets.

Run:
    python generator/generate_replies.py

Input:  data/tickets.jsonl
Output: results/replies.jsonl

Each output record:
{
    "ticket_id": "ticket_001",
    "category": "...",
    "is_adversarial": false,
    "adversarial_type": null,
    "mood": "...",
    "customer_msg": "...",
    "reply_text": "...",
    "confidence": "high | medium | low",
    "abstain": false,
    "abstain_reason": null | "missing_order_info | policy_ambiguous | out_of_scope"
}

Design notes:
- Policy snippet is fetched via get_policy(category) — O(1) lookup, no embeddings.
- Structured JSON output is requested via the prompt; response is parsed and validated.
- Abstain flag is set by the *model* based on the prompt instructions, not post-hoc.
- Low-confidence abstentions get an abstain_reason for the report.
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

# Allow running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data.policy_snippets import get_policy

load_dotenv()

genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

MODEL = os.getenv("GENERATOR_MODEL", "gemini-3.1-flash-lite")

REPLY_PROMPT = """
You are an expert customer support agent at a SaaS/e-commerce company.
Your job is to draft a reply to the customer email below, grounded in the company policy provided.

--- COMPANY POLICY ({category}) ---
{policy}
--- END POLICY ---

--- CUSTOMER EMAIL ---
Mood detected: {mood}
{customer_msg}
--- END EMAIL ---

Instructions:
1. Draft a helpful, empathetic, professional reply that FULLY addresses the customer's issue.
2. Ground every claim in the policy above. Do NOT invent policy details not stated above.
3. Match tone to mood: for angry/frustrated customers, lead with empathy; for neutral/polite, be friendly and efficient.
4. If the customer's request VIOLATES policy (e.g. refund past the window), politely explain why you cannot fulfill it and offer an alternative if one exists.
5. Set abstain=true ONLY if:
   - Critical info needed to resolve the issue is missing (e.g. no order ID, no dates given),
   - The request is in a genuine policy gray zone with no clear answer,
   - The request is completely outside the scope of customer support (e.g. legal threats, media inquiries).
6. Set confidence based on how certain you are the reply is correct and complete.

Return ONLY a valid JSON object with EXACTLY these fields (no markdown, no extra text):
{{
  "reply_text": "<your full reply, 3-8 sentences, professional email format>",
  "confidence": "high | medium | low",
  "abstain": true | false,
  "abstain_reason": "missing_order_info | policy_ambiguous | out_of_scope | null"
}}

If abstain is false, abstain_reason must be null.
If abstain is true, reply_text should be a brief internal note explaining what info is needed (not a customer-facing reply).
""".strip()


def call_gemini(prompt: str, retries: int = 3) -> str:
    model = genai.GenerativeModel(MODEL)
    for attempt in range(retries):
        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=1024,
                ),
            )
            return response.text
        except Exception as exc:
            if attempt < retries - 1:
                wait = 2 ** attempt
                time.sleep(wait)
            else:
                raise


def parse_reply_json(text: str) -> dict:
    """Parse and validate the structured JSON reply from Gemini."""
    # Strip markdown fences
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    # Find first { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in response: {text[:200]}")
    obj = json.loads(text[start : end + 1])

    # Validate required fields
    required = ["reply_text", "confidence", "abstain", "abstain_reason"]
    for field in required:
        if field not in obj:
            raise ValueError(f"Missing field '{field}' in response: {obj}")

    # Normalize
    obj["confidence"] = obj["confidence"].lower().strip()
    if obj["confidence"] not in ("high", "medium", "low"):
        obj["confidence"] = "low"

    obj["abstain"] = bool(obj["abstain"])
    if not obj["abstain"]:
        obj["abstain_reason"] = None

    return obj


def generate_reply(ticket: dict) -> dict:
    """Generate a reply for a single ticket."""
    policy = get_policy(ticket["category"])
    prompt = REPLY_PROMPT.format(
        category=ticket["category"],
        policy=policy,
        mood=ticket.get("mood", "neutral"),
        customer_msg=ticket["customer_msg"],
    )
    raw = call_gemini(prompt)
    reply_data = parse_reply_json(raw)

    return {
        "ticket_id": ticket["id"],
        "category": ticket["category"],
        "is_adversarial": ticket.get("is_adversarial", False),
        "adversarial_type": ticket.get("adversarial_type"),
        "mood": ticket.get("mood", "neutral"),
        "customer_msg": ticket["customer_msg"],
        **reply_data,
    }


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tickets_path = os.path.join(base_dir, "data", "tickets.jsonl")
    output_path = os.path.join(base_dir, "results", "replies.jsonl")

    if not os.path.exists(tickets_path):
        print(f"ERROR: {tickets_path} not found. Run data/generate_dataset.py first.")
        sys.exit(1)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Load tickets
    tickets = []
    with open(tickets_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tickets.append(json.loads(line))

    print("=" * 60)
    print(f"Reply Generator — {len(tickets)} tickets, model: {MODEL}")
    print("=" * 60)

    replies = []
    errors = []

    with open(output_path, "w", encoding="utf-8") as out_f:
        for ticket in tqdm(tickets, desc="Generating replies"):
            try:
                reply = generate_reply(ticket)
                replies.append(reply)
                out_f.write(json.dumps(reply) + "\n")
                out_f.flush()
            except Exception as exc:
                print(f"\n  [ERROR] ticket {ticket['id']}: {exc}")
                errors.append(ticket["id"])
            time.sleep(0.3)  # gentle rate-limiting

    # Summary
    abstained = [r for r in replies if r["abstain"]]
    adv_replies = [r for r in replies if r["is_adversarial"]]
    adv_abstained = [r for r in adv_replies if r["abstain"]]

    print(f"\n{'='*60}")
    print(f"Done. {len(replies)} replies written to {output_path}")
    print(f"  Abstained:            {len(abstained)}/{len(replies)} ({len(abstained)/max(len(replies),1)*100:.1f}%)")
    print(f"  Adversarial abstained:{len(adv_abstained)}/{len(adv_replies)}")
    if errors:
        print(f"  Errors ({len(errors)}):       {errors}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
