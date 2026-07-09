"""
policy_snippets.py — Category-specific policy context for reply grounding.

Design decision: a simple dict lookup instead of embeddings/RAG.
Rationale: With only 5 categories and stable policy text, vector search adds
latency and complexity with zero accuracy benefit. The generator gets the exact
right snippet every time via O(1) lookup.
"""

POLICY_SNIPPETS: dict[str, str] = {
    "billing": """
BILLING POLICY:
- Customers are charged on the 1st of each month for the current billing cycle.
- Invoices are emailed within 24 hours of a charge being processed.
- Billing disputes must be raised within 30 days of the charge date.
- Accepted payment methods: credit/debit cards (Visa, Mastercard, Amex) and bank transfers.
- Failed payments are retried up to 3 times over 7 days before the account is suspended.
- Customers can update their payment method at any time from Account Settings → Billing.
- Pro-rated refunds are issued if a paid plan is downgraded within the first 7 days of a billing cycle.
- VAT/GST is applied based on the customer's registered country of residence.
- Annual plan holders receive a 20% discount and are billed once per year; no monthly pro-ration.
- Receipts and tax invoices are available for download in Account Settings → Billing History.
""",

    "shipping": """
SHIPPING POLICY:
- Standard shipping: 5–7 business days (free on orders over $50).
- Express shipping: 2–3 business days ($12.99 flat fee).
- Overnight shipping: next business day if ordered before 2 PM EST ($24.99 flat fee).
- Orders are processed within 1 business day of placement (excluding weekends and public holidays).
- A tracking number is emailed once the order ships; allow 24 hours for tracking to activate.
- We ship to all 50 US states and 40+ international destinations; international delivery takes 10–14 business days.
- Customs duties and import taxes are the customer's responsibility for international orders.
- Lost or damaged packages must be reported within 14 days of the expected delivery date.
- Address changes after order placement can only be accommodated within 2 hours of order confirmation.
- Signature-on-delivery is required for orders over $200.
""",

    "refund": """
REFUND POLICY:
- Refund window: 30 days from delivery date for physical goods; 14 days for digital/software products.
- Items must be unused, in original packaging, with all accessories included.
- Refund processing time: 3–5 business days after the returned item is received and inspected.
- Refunds are issued to the original payment method only; no cash refunds or store-credit substitutions unless the original method is unavailable.
- Return shipping costs are borne by the customer unless the return is due to a defective item or our shipping error.
- Digital products are non-refundable after the license key has been activated, unless the product is non-functional as described.
- Partial refunds may be issued for items returned in a condition different from when sold.
- Subscription cancellations do not automatically trigger a refund; the customer retains access until the end of the paid period.
- Gift purchases can be refunded to store credit at the recipient's request.
- Bulk/enterprise orders are subject to a separate refund agreement outlined in the master service contract.
""",

    "bug": """
BUG REPORT & TECHNICAL SUPPORT POLICY:
- All bug reports are triaged within 1 business day and assigned a severity level (P1–P4).
- P1 (system down / data loss): target resolution within 4 hours, 24/7 on-call team engaged.
- P2 (major feature broken): target resolution within 1 business day.
- P3 (minor feature impaired, workaround available): resolved in next scheduled release sprint (typically 2 weeks).
- P4 (cosmetic / enhancement request): added to backlog; no committed timeline.
- To expedite triage, please provide: browser/OS version, steps to reproduce, screenshots or screen recordings, and any error messages.
- Customers on Enterprise plans receive a dedicated Technical Account Manager and a private Slack channel for P1/P2 incidents.
- Known issues are tracked on our public status page: status.example.com.
- We do not support beta/preview versions of third-party browsers or operating systems.
- Security vulnerabilities should be reported via our responsible disclosure program, not through the standard support queue.
""",

    "churn-risk": """
RETENTION & CANCELLATION POLICY:
- Customers wishing to cancel can do so at any time from Account Settings → Subscription → Cancel Plan.
- Before cancellation takes effect, we offer a 1-time retention option: a 30% discount for the next 3 months, or a plan downgrade with no penalty.
- Cancelled accounts retain read-only data access for 60 days after the subscription end date.
- Data export is available at any time before and within 60 days after cancellation.
- Reactivation within 60 days restores all data; after 60 days data is permanently deleted.
- Customers on annual plans who cancel mid-year are not entitled to a pro-rated refund unless covered by our 30-day money-back guarantee (new customers only).
- Enterprise customers must follow the cancellation procedure in their master service agreement; standard self-serve cancellation is not available.
- If cancellation is driven by a pricing concern, escalate to the Account Management team who have authority to offer custom pricing.
- Customer success check-ins are available free of charge; customers can book a 30-minute call to address product concerns before deciding to cancel.
- We collect cancellation reasons to improve the product; sharing a reason is optional but appreciated.
""",
}


def get_policy(category: str) -> str:
    """Return the policy snippet for a given ticket category.

    Args:
        category: One of billing, shipping, refund, bug, churn-risk.

    Returns:
        Policy text string. Falls back to a generic message if category unknown.
    """
    return POLICY_SNIPPETS.get(
        category.lower().strip(),
        "GENERAL SUPPORT POLICY: Always be helpful, accurate, and empathetic. "
        "Escalate to a human agent if you are unsure.",
    )
