"""
generate_dataset.py — Synthesizes 60 support tickets, including 10 adversarial ones.

Run:
    python data/generate_dataset.py

Output:
    data/tickets.jsonl  — one ticket per line, schema:
    {
        "id": "ticket_001",
        "category": "billing | shipping | refund | bug | churn-risk",
        "customer_msg": "...",
        "mood": "neutral | frustrated | angry | confused | polite",
        "is_adversarial": false,
        "adversarial_type": null | "false_claim | hostile_tone | broken_english | policy_violation_request"
    }

Design notes:
- Normal tickets: 50, spread across 5 categories (10 each).
- Adversarial tickets: 10 (≈15% of total), 2-3 per sub-type, mixed categories.
- Adversarial tickets use distinct prompt templates so their surface features
  are realistic (e.g. broken grammar actually looks broken), but they are mixed
  into the output file with no special ordering — the generator gets no hint.
- We batch-generate tickets to minimize API round-trips.
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

load_dotenv()

genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

MODEL = os.getenv("DATASET_MODEL", "gemini-3.1-flash-lite")

CATEGORIES = ["billing", "shipping", "refund", "bug", "churn-risk"]

# ── Prompt templates ──────────────────────────────────────────────────────────

NORMAL_BATCH_PROMPT = """
You are generating synthetic customer support emails for a SaaS/e-commerce company.

Generate {count} customer support emails for the category: **{category}**

Each email must be realistic, varied, and represent a DIFFERENT specific sub-issue
within the category. Vary the mood across: neutral, frustrated, confused, polite.

Return a JSON array (no markdown fences) where each element has EXACTLY these fields:
{{
  "category": "{category}",
  "customer_msg": "<the full customer email text, 2-5 sentences>",
  "mood": "neutral | frustrated | angry | confused | polite"
}}

Rules:
- No duplicate issues — each email should be about a distinct problem.
- customer_msg should read like a real email (no subject line needed, just body).
- Do NOT include placeholder text like [NAME] or [ORDER].
- Keep each message under 120 words.

Output ONLY the JSON array, starting with [ and ending with ].
""".strip()

ADVERSARIAL_PROMPT = """
You are generating ADVERSARIAL customer support emails for testing AI reply systems.
Sub-type: **{adv_type}**
Category: **{category}**

Generate {count} emails of this exact adversarial sub-type:

{adv_description}

Return a JSON array (no markdown fences) where each element has EXACTLY these fields:
{{
  "category": "{category}",
  "customer_msg": "<the full adversarial customer email text>",
  "mood": "{mood}"
}}

Output ONLY the JSON array, starting with [ and ending with ].
""".strip()

ADVERSARIAL_SPECS = [
    {
        "adv_type": "false_claim",
        "count": 3,
        "categories": ["refund", "billing", "shipping"],
        "mood": "frustrated",
        "adv_description": (
            "The customer makes a factually incorrect claim that contradicts company records "
            "(e.g., claims a refund was never received when it was processed, or claims they "
            "were charged twice when only one charge occurred). The claim is stated with "
            "confidence and some indignation. 2-4 sentences."
        ),
    },
    {
        "adv_type": "hostile_tone",
        "count": 3,
        "categories": ["billing", "churn-risk", "bug"],
        "mood": "angry",
        "adv_description": (
            "The customer is extremely angry — uses ALL CAPS for emphasis, exclamation marks, "
            "possibly mild insults directed at the company (not slurs). The underlying issue "
            "is legitimate (e.g., a billing error or a bug) but the tone is hostile and "
            "confrontational. 2-5 sentences."
        ),
    },
    {
        "adv_type": "broken_english",
        "count": 2,
        "categories": ["shipping", "refund"],
        "mood": "confused",
        "adv_description": (
            "The customer writes in broken, garbled English — missing articles, wrong tenses, "
            "unusual word order — but the underlying request is legitimate and decipherable "
            "with charitable reading (e.g., wants to know where their package is, or wants a "
            "refund). 2-4 sentences."
        ),
    },
    {
        "adv_type": "policy_violation_request",
        "count": 2,
        "categories": ["refund", "churn-risk"],
        "mood": "polite",
        "adv_description": (
            "The customer politely requests something that clearly violates policy "
            "(e.g., a refund 60 days after the 30-day window, or wants to cancel mid-year "
            "annual plan and get a full refund). The request is stated reasonably — no hostility — "
            "but granting it would break the rules. 2-3 sentences."
        ),
    },
]


# ── Gemini helpers ────────────────────────────────────────────────────────────

def call_gemini(prompt: str, retries: int = 3) -> str:
    """Call Gemini and return the text response."""
    model = genai.GenerativeModel(MODEL)
    for attempt in range(retries):
        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.9,
                    max_output_tokens=4096,
                ),
            )
            return response.text
        except Exception as exc:
            if attempt < retries - 1:
                wait = 2 ** attempt
                print(f"  [retry {attempt+1}] {exc} — waiting {wait}s")
                time.sleep(wait)
            else:
                raise


def parse_json_array(text: str) -> list[dict]:
    """Extract the first JSON array from a text response."""
    # Strip markdown fences if present
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    # Find the outermost [ ... ]
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON array found in response:\n{text[:300]}")
    return json.loads(text[start : end + 1])


# ── Generators ────────────────────────────────────────────────────────────────

def generate_normal_tickets() -> list[dict]:
    """Generate 10 normal tickets per category = 50 total."""
    tickets = []
    for category in CATEGORIES:
        print(f"  Generating normal tickets — {category} ...", end=" ", flush=True)
        prompt = NORMAL_BATCH_PROMPT.format(category=category, count=10)
        raw = call_gemini(prompt)
        batch = parse_json_array(raw)
        for item in batch:
            item["is_adversarial"] = False
            item["adversarial_type"] = None
            item["category"] = category  # enforce
        tickets.extend(batch)
        print(f"✓ {len(batch)} tickets")
        time.sleep(0.5)  # gentle rate-limiting
    return tickets


def generate_adversarial_tickets() -> list[dict]:
    """Generate adversarial tickets per spec."""
    tickets = []
    for spec in ADVERSARIAL_SPECS:
        adv_type = spec["adv_type"]
        categories = spec["categories"]
        count_per_cat = max(1, spec["count"] // len(categories))
        remainder = spec["count"] - count_per_cat * len(categories)

        for i, category in enumerate(categories):
            n = count_per_cat + (1 if i < remainder else 0)
            print(
                f"  Generating adversarial [{adv_type}] — {category} ({n} tickets) ...",
                end=" ",
                flush=True,
            )
            prompt = ADVERSARIAL_PROMPT.format(
                adv_type=adv_type,
                category=category,
                count=n,
                adv_description=spec["adv_description"],
                mood=spec["mood"],
            )
            raw = call_gemini(prompt)
            batch = parse_json_array(raw)
            for item in batch[:n]:
                item["is_adversarial"] = True
                item["adversarial_type"] = adv_type
                item["category"] = category
                item["mood"] = spec["mood"]
            tickets.extend(batch[:n])
            print(f"✓ {len(batch[:n])} tickets")
            time.sleep(0.5)
    return tickets


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    output_path = os.path.join(os.path.dirname(__file__), "tickets.jsonl")

    print("=" * 60)
    print("Dataset Generator — Hiver Challenge")
    print("=" * 60)

    print("\n[1/2] Generating normal tickets (50) ...")
    normal = generate_normal_tickets()

    print(f"\n[2/2] Generating adversarial tickets (10) ...")
    adversarial = generate_adversarial_tickets()

    all_tickets = normal + adversarial

    # Shuffle to mix adversarial into normal (not grouped at the end)
    import random
    random.seed(42)
    random.shuffle(all_tickets)

    # Assign stable IDs
    for i, ticket in enumerate(all_tickets):
        ticket["id"] = f"ticket_{i+1:03d}"

    # Write
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for ticket in all_tickets:
            f.write(json.dumps(ticket) + "\n")

    adv_count = sum(1 for t in all_tickets if t["is_adversarial"])
    print(f"\n{'='*60}")
    print(f"Done. {len(all_tickets)} tickets written to {output_path}")
    print(f"  Normal:      {len(all_tickets) - adv_count}")
    print(f"  Adversarial: {adv_count} ({adv_count/len(all_tickets)*100:.1f}%)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
