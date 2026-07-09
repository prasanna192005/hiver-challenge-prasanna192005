"""
customer_simulator.py — Multi-turn simulation of the customer responding to the AI reply.

Run:
    python eval/customer_simulator.py

Input:  results/replies.jsonl
Output: results/simulation.jsonl

Each output record:
{
    "ticket_id": "ticket_001",
    "category": "...",
    "is_adversarial": false,
    "adversarial_type": null,
    "skipped": false,
    "conversation": [
        {"role": "support", "text": "..."},
        {"role": "customer", "text": "..."},
        ...
    ],
    "outcome": "resolved | partially_resolved | not_resolved",
    "turns_to_resolve": 1,
    "had_to_repeat_ask": false
}

Design notes:
- Customer persona is primed with the original mood AND original issue.
- Simulation runs 2-3 turns max to keep costs bounded.
- Final turn always includes an outcome assessment call to the model.
- Abstained tickets are skipped — correctly, since no reply was sent.
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

MODEL = os.getenv("SIMULATOR_MODEL", "gemini-3.1-flash-lite")
MAX_TURNS = 3

CUSTOMER_SYSTEM_PROMPT = """
You are roleplaying as a customer who sent a support email. 
Your original issue: {original_issue}
Your mood: {mood}

Stay in character as this customer. Respond to the support agent's reply.
- If the reply fully resolves your issue, say so and thank them (keep it brief).
- If the reply partially addresses your issue, ask a follow-up question about what wasn't resolved.
- If the reply ignores your question or gives wrong information, express your frustration and repeat your ask.
- If the reply asks for information, provide what you can from your original message.

IMPORTANT: After your customer response, on a NEW LINE, output EXACTLY one of these verdict labels:
VERDICT: RESOLVED
VERDICT: PARTIALLY_RESOLVED
VERDICT: NOT_RESOLVED

The verdict reflects whether YOUR issue is resolved after reading the support reply.
Keep your customer response to 2-4 sentences max.
""".strip()

FINAL_ASSESSMENT_PROMPT = """
Based on this customer support conversation, provide a final outcome assessment.

Original issue: {original_issue}
Original mood: {mood}

Conversation:
{conversation_text}

Answer with ONLY a JSON object (no markdown):
{{
  "outcome": "resolved | partially_resolved | not_resolved",
  "had_to_repeat_ask": true | false,
  "assessment_note": "<one sentence explaining the outcome>"
}}

had_to_repeat_ask = true if the customer had to ask the same question more than once.
""".strip()


def call_gemini_chat(
    messages: list[dict],
    system_prompt: str | None = None,
    retries: int = 3,
) -> str:
    """Call Gemini with multi-turn chat history."""
    model = genai.GenerativeModel(
        MODEL,
        system_instruction=system_prompt,
    )
    history = []
    for msg in messages[:-1]:
        history.append(
            {"role": msg["role"], "parts": [{"text": msg["content"]}]}
        )
    last = messages[-1]
    chat = model.start_chat(history=history)
    for attempt in range(retries):
        try:
            response = chat.send_message(
                last["content"],
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
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


def call_gemini_simple(prompt: str, retries: int = 3) -> str:
    model = genai.GenerativeModel(MODEL)
    for attempt in range(retries):
        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=256,
                ),
            )
            return response.text
        except Exception as exc:
            if attempt < retries - 1:
                wait = 2 ** attempt
                time.sleep(wait)
            else:
                raise


def parse_verdict(text: str) -> str | None:
    """Extract VERDICT: <label> from customer response."""
    match = re.search(r"VERDICT:\s*(RESOLVED|PARTIALLY_RESOLVED|NOT_RESOLVED)", text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


def clean_customer_text(text: str) -> str:
    """Remove the VERDICT line from the customer's visible response."""
    lines = text.strip().split("\n")
    cleaned = [l for l in lines if not re.match(r"\s*VERDICT:", l, re.IGNORECASE)]
    return "\n".join(cleaned).strip()


def simulate_conversation(reply: dict) -> dict:
    """Run 2-3 turn customer simulation for a single reply."""
    ticket_id = reply["ticket_id"]
    original_issue = reply["customer_msg"]
    mood = reply.get("mood", "neutral")
    initial_reply = reply["reply_text"]

    system_prompt = CUSTOMER_SYSTEM_PROMPT.format(
        original_issue=original_issue,
        mood=mood,
    )

    conversation = [
        {"role": "support", "text": initial_reply},
    ]

    # Track verdicts per turn
    verdicts = []
    messages = [
        {"role": "user", "content": f"[Support Agent's Reply]: {initial_reply}"},
    ]

    for turn in range(MAX_TURNS):
        # Customer responds
        customer_raw = call_gemini_chat(messages, system_prompt=system_prompt)
        verdict = parse_verdict(customer_raw)
        customer_text = clean_customer_text(customer_raw)

        conversation.append({"role": "customer", "text": customer_text})
        if verdict:
            verdicts.append(verdict)

        # If resolved, stop early
        if verdict == "RESOLVED":
            break

        # Support replies again (simple, policy-grounded follow-up)
        messages.append({"role": "model", "content": customer_text})
        if turn < MAX_TURNS - 1:
            support_followup_prompt = (
                f"You are a professional customer support agent. "
                f"The customer sent this follow-up: {customer_text}\n\n"
                f"Original issue context: {original_issue}\n"
                f"Give a brief, helpful follow-up reply (2-4 sentences). "
                f"Do not generate a VERDICT line."
            )
            support_raw = call_gemini_simple(support_followup_prompt)
            conversation.append({"role": "support", "text": support_raw.strip()})
            messages.append({"role": "user", "content": support_raw.strip()})

        time.sleep(0.2)

    # Final outcome assessment
    conv_text = "\n".join(
        f"[{turn['role'].upper()}]: {turn['text']}" for turn in conversation
    )
    assessment_prompt = FINAL_ASSESSMENT_PROMPT.format(
        original_issue=original_issue,
        mood=mood,
        conversation_text=conv_text,
    )
    assessment_raw = call_gemini_simple(assessment_prompt)

    # Parse assessment
    try:
        assessment_text = re.sub(r"```(?:json)?", "", assessment_raw).strip().rstrip("`").strip()
        start = assessment_text.find("{")
        end = assessment_text.rfind("}")
        assessment = json.loads(assessment_text[start : end + 1])
        outcome = assessment.get("outcome", "not_resolved")
        had_to_repeat = bool(assessment.get("had_to_repeat_ask", False))
    except Exception:
        # Fall back to last verdict
        if verdicts and verdicts[-1] == "RESOLVED":
            outcome = "resolved"
        elif verdicts and verdicts[-1] == "PARTIALLY_RESOLVED":
            outcome = "partially_resolved"
        else:
            outcome = "not_resolved"
        had_to_repeat = len(conversation) > 3

    turns_to_resolve = len([t for t in conversation if t["role"] == "support"])

    return {
        "ticket_id": ticket_id,
        "category": reply["category"],
        "is_adversarial": reply.get("is_adversarial", False),
        "adversarial_type": reply.get("adversarial_type"),
        "skipped": False,
        "conversation": conversation,
        "outcome": outcome,
        "turns_to_resolve": turns_to_resolve,
        "had_to_repeat_ask": had_to_repeat,
    }


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    replies_path = os.path.join(base_dir, "results", "replies.jsonl")
    output_path = os.path.join(base_dir, "results", "simulation.jsonl")

    if not os.path.exists(replies_path):
        print(f"ERROR: {replies_path} not found.")
        sys.exit(1)

    replies = []
    with open(replies_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                replies.append(json.loads(line))

    print("=" * 60)
    print(f"Customer Simulator — {len(replies)} replies, model: {MODEL}")
    print("=" * 60)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    results = []
    errors = []

    with open(output_path, "w", encoding="utf-8") as out_f:
        for reply in tqdm(replies, desc="Simulating conversations"):
            ticket_id = reply["ticket_id"]

            # Skip abstained — nothing was sent
            if reply.get("abstain", False):
                skipped_record = {
                    "ticket_id": ticket_id,
                    "category": reply["category"],
                    "is_adversarial": reply.get("is_adversarial", False),
                    "adversarial_type": reply.get("adversarial_type"),
                    "skipped": True,
                    "conversation": [],
                    "outcome": "abstained",
                    "turns_to_resolve": 0,
                    "had_to_repeat_ask": False,
                }
                results.append(skipped_record)
                out_f.write(json.dumps(skipped_record) + "\n")
                continue

            try:
                sim = simulate_conversation(reply)
                results.append(sim)
                out_f.write(json.dumps(sim) + "\n")
                out_f.flush()
            except Exception as exc:
                print(f"\n  [ERROR] {ticket_id}: {exc}")
                errors.append(ticket_id)
            time.sleep(0.5)

    # Stats
    simulated = [r for r in results if not r["skipped"]]
    resolved = [r for r in simulated if r["outcome"] == "resolved"]
    partial = [r for r in simulated if r["outcome"] == "partially_resolved"]
    not_res = [r for r in simulated if r["outcome"] == "not_resolved"]
    repeated = [r for r in simulated if r["had_to_repeat_ask"]]

    print(f"\n{'='*60}")
    print(f"Done. {len(results)} records written to {output_path}")
    print(f"  Simulated:         {len(simulated)}")
    print(f"  Resolved:          {len(resolved)}")
    print(f"  Partially resolved:{len(partial)}")
    print(f"  Not resolved:      {len(not_res)}")
    print(f"  Had to repeat ask: {len(repeated)}")
    if errors:
        print(f"  Errors ({len(errors)}): {errors}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
