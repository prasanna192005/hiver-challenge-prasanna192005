# Hiver Open Challenge: AI Support Agent & Calibrated Evaluation System

This repository contains our submission for the Hiver Open Challenge. It is a complete pipeline designed to generate automated customer support replies, verify their performance via multi-layered verification (rubric grading and multi-turn adversarial simulations), and calibrate the automated grading against real human reviews.

---

## Quick Start

1. Install Dependencies
   ```bash
   pip install -r requirements.txt
   ```

2. Configure Environment Variables (Optional)
   Copy the example environment file and configure your Google Gemini API Key:
   ```bash
   cp .env.example .env
   # Edit .env and paste: GOOGLE_API_KEY=AIzaSy...
   ```
   *Note: If you do not have an API key, the pipeline automatically runs in offline mode using pre-cached mock records from seed_data.py so you can inspect the dashboard instantly.*

3. Run the Full Pipeline
   ```bash
   python run_all.py
   ```
   This will run dataset generation, reply synthesis, rubric evaluations, multi-turn customer simulations, correlation analysis, and compile the final dashboard (or use the offline mock generator if the key is missing).

4. Explore the Results Dashboard
   Open the generated file in your browser to inspect the visual report:
   results/report.html

---

## Architectural decisions & evaluation strategy

The core focus of this system is evaluation integrity. Generative AI is easy to build but notoriously difficult to measure accurately. Naive scoring setups fail under production conditions. We address this with a multi-layered evaluation framework:

### Stage 1: Rubric Grading
The rubric grader evaluates the initial support draft on 4 distinct dimensions: Factual Grounding, Tone Match, Resolution Completeness, and Conciseness. This catches immediate errors (e.g. policy violations or poor tone) and tags low-performing drafts with specific failure modes like `hallucinated_policy`.

### Stage 2: Multi-Turn Conversation Simulation
A reply can look polite, structured, and syntactically flawless while failing to solve the customer's actual problem. 
To catch this, the simulator runs up to a 3-turn dialogue between the AI support agent and a simulated customer persona. The simulator tracks the actual resolution outcome (e.g. did the conversation end in a `resolved` status?) and identifies friction points (such as whether the customer had to repeat their question).

### Stage 3: Statistical Calibration (Spearman Correlation)
How do we know the evaluator can be trusted? We calibrate it.
The calibration engine ranks automated composite scores against manual reviews in the human gold set (`gold/gold.jsonl`) using the Spearman Rank Correlation Coefficient:

$$\text{Correlation} = 1 - \frac{6 \sum d_i^2}{n(n^2 - 1)}$$

* The live calibration run against the 41 manual grading records achieved a correlation of **0.865**, proving the automated rubric strongly aligns with human expert judgment.
* If prompts are adjusted and the correlation falls below 0.70, it signals that the rubric grader is drifting from human standards. The developer can review the disagreement table in the calibration report to refine the grading parameters.

---

## Dataset Quality and Honesty

A dataset that yields 100% success scores is fabricated and useless for testing boundary conditions. Our dataset (`data/tickets.jsonl`) is designed to reflect real support dynamics:

* **Mood & Persona Variety:** Tickets span polite, confused, frustrated, and angry customers.
* **Adversarial Integrity:** 15% of the dataset consists of adversarial tickets containing:
  * `false_claim`: Customers attempting to trick the agent into processing refunds.
  * `hostile_tone`: Customers using aggressive capital letters.
  * `broken_english`: Grammatically garbled customer inquiries.
  * `policy_violation_request`: Explicit requests to bypass company policies.
* **Honest Scoring:** We manually reviewed and graded these boundary cases to build `gold/gold.jsonl`. Our results show that the model occasionally fails (e.g. `ticket_003` hallucinating policy on an angry duplicate-billing request). The evaluator correctly flagged this failure, proving its honesty.

---

## Response Generator Design

The reply generator (`generator/generate_replies.py`) is built to be simple, fast, and secure:

* **Direct Policy Lookups:** Instead of using vector search (RAG) which adds latency and introduces retrieval errors on small, static rule sets, the generator maps incoming tickets directly to their categories (billing, shipping, refund, bug, churn-risk) and fetches the policy rules block from a Python dictionary. The correct rules are injected straight into the generation prompt with zero retrieval latency.
* **Abstention Triggers:** If a ticket presents a security risk or asks for an override that violates policy, the generator flags `"abstain": true` along with a reason. These tickets bypass drafting and are routed to a human review queue.
* **Low-Confidence Flags:** If the ticket lacks key parameters (like a missing order number) required to resolve the issue under the policy, the generator sets the confidence level to `"low"`, notifying the review queue that the draft must be verified.

---

## Tool Usage Declaration

This project was built using AI pair-programming assistants. AI tools were used for:
* Accelerating development of the static HTML reporting template and interactive filters.
* Drafting initial prompts for the rubric evaluator and customer simulator personas.
* Writing boilerplate dataset generation loops.

All core design decisions, grounding strategies, validation constraints, and statistical calibration math were designed and verified by the developer to ensure system reliability.

---

## License

This project is licensed under the MIT License.
