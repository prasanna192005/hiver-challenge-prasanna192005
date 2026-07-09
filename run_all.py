"""
run_all.py — End-to-end orchestrator for the Hiver AI Email Eval System.

Usage:
    python run_all.py                  # full pipeline
    python run_all.py --skip-dataset   # skip dataset generation (use existing tickets.jsonl)
    python run_all.py --skip-replies   # also skip reply generation
    python run_all.py --report-only    # only regenerate the HTML report

Steps:
    1. Generate dataset (data/tickets.jsonl)
    2. Generate replies (results/replies.jsonl)
    3. Grade replies with rubric (results/scores.jsonl)
    4. Simulate customer conversations (results/simulation.jsonl)
    5. Build HTML report (results/report.html)
    6. Run calibration if gold set has human scores (results/calibration_report.md)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "results")


# ── Runner helpers ────────────────────────────────────────────────────────────

def run_step(script_path: str, step_name: str) -> bool:
    """Run a Python script as a subprocess, streaming output."""
    print(f"\n{'='*60}")
    print(f"  STEP: {step_name}")
    print(f"{'='*60}")
    start = time.time()
    result = subprocess.run(
        [sys.executable, script_path],
        cwd=BASE_DIR,
    )
    elapsed = time.time() - start
    if result.returncode == 0:
        print(f"  ✓ {step_name} completed in {elapsed:.1f}s")
        return True
    else:
        print(f"  ✗ {step_name} FAILED (exit code {result.returncode})")
        return False


def load_jsonl(path: str) -> list[dict]:
    records = []
    if not os.path.exists(path):
        return records
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# ── HTML Report Builder ───────────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Hiver AI Email Eval — Report</title>
  <style>
    :root {{
      --bg: #0f1117;
      --surface: #1a1d27;
      --surface2: #22263a;
      --border: #2e3354;
      --accent: #6c63ff;
      --accent2: #00d4aa;
      --accent3: #ff6b6b;
      --text: #e4e6f0;
      --text-muted: #8b93b5;
      --green: #22c55e;
      --yellow: #f59e0b;
      --red: #ef4444;
      --orange: #f97316;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      min-height: 100vh;
    }}
    .header {{
      background: linear-gradient(135deg, #1a1d27 0%, #12152b 100%);
      border-bottom: 1px solid var(--border);
      padding: 2rem 3rem;
    }}
    .header h1 {{
      font-size: 1.8rem;
      font-weight: 700;
      background: linear-gradient(90deg, #6c63ff, #00d4aa);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      margin-bottom: 0.25rem;
    }}
    .header .subtitle {{ color: var(--text-muted); font-size: 0.9rem; }}
    .container {{ max-width: 1600px; margin: 0 auto; padding: 2rem 3rem; }}
    
    /* Metric Cards */
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }}
    .metric-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.25rem 1.5rem;
      transition: transform 0.2s, box-shadow 0.2s;
    }}
    .metric-card:hover {{ transform: translateY(-2px); box-shadow: 0 8px 24px rgba(108,99,255,0.15); }}
    .metric-card .label {{ color: var(--text-muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; }}
    .metric-card .value {{ font-size: 2rem; font-weight: 700; }}
    .metric-card .sub {{ font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem; }}
    .value.good {{ color: var(--green); }}
    .value.warn {{ color: var(--yellow); }}
    .value.bad  {{ color: var(--red); }}
    .value.accent {{ color: var(--accent); }}
    .value.accent2 {{ color: var(--accent2); }}

    /* Sections */
    .section {{ margin-bottom: 2.5rem; }}
    .section-title {{
      font-size: 1.1rem;
      font-weight: 600;
      color: var(--accent2);
      border-left: 3px solid var(--accent2);
      padding-left: 0.75rem;
      margin-bottom: 1rem;
    }}

    /* Compare cards */
    .compare-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
      margin-bottom: 2rem;
    }}
    .compare-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.5rem;
    }}
    .compare-card h3 {{ font-size: 0.95rem; margin-bottom: 1rem; }}
    .compare-card.normal h3 {{ color: var(--accent2); }}
    .compare-card.adversarial h3 {{ color: var(--accent3); }}
    .score-row {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }}
    .score-row .dim {{ font-size: 0.85rem; color: var(--text-muted); }}
    .score-bar {{ flex: 1; margin: 0 1rem; height: 6px; background: var(--surface2); border-radius: 3px; overflow: hidden; }}
    .score-bar-fill {{ height: 100%; border-radius: 3px; transition: width 0.5s; }}
    .score-val {{ font-size: 0.85rem; font-weight: 600; min-width: 30px; text-align: right; }}

    /* Failure mode table */
    .failure-table {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      margin-bottom: 2rem;
    }}
    .failure-table table {{ width: 100%; border-collapse: collapse; }}
    .failure-table th {{
      background: var(--surface2);
      padding: 0.75rem 1rem;
      text-align: left;
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border);
    }}
    .failure-table td {{ padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); font-size: 0.9rem; }}
    .failure-table tr:last-child td {{ border-bottom: none; }}
    .failure-table tr:hover td {{ background: var(--surface2); }}
    .tag {{
      display: inline-block;
      padding: 0.2rem 0.6rem;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 600;
      letter-spacing: 0.02em;
    }}
    .tag-red {{ background: rgba(239,68,68,0.15); color: #f87171; }}
    .tag-orange {{ background: rgba(249,115,22,0.15); color: #fb923c; }}
    .tag-yellow {{ background: rgba(245,158,11,0.15); color: #fbbf24; }}
    .tag-purple {{ background: rgba(108,99,255,0.15); color: #a78bfa; }}
    .tag-green {{ background: rgba(34,197,94,0.15); color: #4ade80; }}
    .tag-gray {{ background: rgba(139,147,181,0.15); color: #8b93b5; }}
    .tag-blue {{ background: rgba(59,130,246,0.15); color: #60a5fa; }}

    /* Main table */
    .main-table-wrapper {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
    }}
    .table-scroll {{ overflow-x: auto; }}
    table.main {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
    table.main th {{
      background: var(--surface2);
      padding: 0.75rem 1rem;
      text-align: left;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
      cursor: pointer;
      user-select: none;
    }}
    table.main th:hover {{ color: var(--accent2); }}
    table.main td {{
      padding: 1rem;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
      max-width: none;
      word-break: break-word;
    }}
    table.main tr:last-child td {{ border-bottom: none; }}
    table.main tr:hover td {{ background: var(--surface-hover); }}
    table.main tr.adversarial td {{ border-left: 3px solid var(--accent3); }}
    table.main tr.abstained td {{ opacity: 0.6; }}
    .msg-cell {{ min-width: 250px; font-size: 0.8rem; }}
    .msg-text {{
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0.75rem;
      color: var(--text);
      max-height: 250px;
      overflow-y: auto;
      white-space: pre-wrap;
      font-family: inherit;
    }}
    .score-chip {{
      display: inline-block;
      padding: 0.15rem 0.5rem;
      border-radius: 4px;
      font-weight: 700;
      font-size: 0.8rem;
    }}
    .sc-5 {{ background: rgba(34,197,94,0.2); color: #4ade80; }}
    .sc-4 {{ background: rgba(132,204,22,0.15); color: #a3e635; }}
    .sc-3 {{ background: rgba(245,158,11,0.15); color: #fbbf24; }}
    .sc-2 {{ background: rgba(249,115,22,0.15); color: #fb923c; }}
    .sc-1 {{ background: rgba(239,68,68,0.2); color: #f87171; }}

    /* Outcome badge */
    .outcome-badge {{
      display: inline-block;
      padding: 0.2rem 0.6rem;
      border-radius: 20px;
      font-size: 0.72rem;
      font-weight: 600;
    }}
    .ob-resolved {{ background: rgba(34,197,94,0.15); color: #4ade80; }}
    .ob-partial {{ background: rgba(245,158,11,0.15); color: #fbbf24; }}
    .ob-not {{ background: rgba(239,68,68,0.15); color: #f87171; }}
    .ob-abstained {{ background: rgba(108,99,255,0.15); color: #a78bfa; }}

    .conf-badge {{
      display: inline-block;
      padding: 0.1rem 0.5rem;
      border-radius: 3px;
      font-size: 0.7rem;
      font-weight: 600;
    }}
    .cb-high {{ color: #4ade80; }}
    .cb-medium {{ color: #fbbf24; }}
    .cb-low {{ color: #f87171; }}

    /* Abstention rate chart */
    .abst-bar {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.25rem 1.5rem;
      margin-bottom: 2rem;
    }}
    .abst-row {{ display: flex; align-items: center; gap: 1rem; margin-bottom: 0.75rem; }}
    .abst-label {{ font-size: 0.85rem; min-width: 140px; }}
    .abst-track {{ flex: 1; height: 10px; background: var(--surface2); border-radius: 5px; overflow: hidden; }}
    .abst-fill {{ height: 100%; border-radius: 5px; }}
    .abst-val {{ font-size: 0.85rem; font-weight: 600; min-width: 60px; text-align: right; }}

    .footer {{
      text-align: center;
      color: var(--text-muted);
      font-size: 0.8rem;
      padding: 2rem;
      border-top: 1px solid var(--border);
      margin-top: 2rem;
    }}

    /* Search */
    .table-controls {{ display: flex; gap: 1rem; margin-bottom: 1rem; align-items: center; flex-wrap: wrap; }}
    .search-box {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.5rem 1rem;
      color: var(--text);
      font-size: 0.9rem;
      outline: none;
      width: 250px;
    }}
    .search-box:focus {{ border-color: var(--accent); }}
    .filter-btn {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.5rem 1rem;
      color: var(--text-muted);
      font-size: 0.85rem;
      cursor: pointer;
      transition: all 0.2s;
    }
    .filter-btn:hover, .filter-btn.active { border-color: var(--accent); color: var(--accent); background: rgba(108,99,255,0.08); }

    /* Modal Backdrop */
    .modal-backdrop {
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      background: rgba(0, 0, 0, 0.75);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 1000;
    }
    /* Modal Container */
    .modal-content {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 8px;
      width: 95%;
      max-width: 1100px;
      max-height: 85vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      animation: fadeIn 0.15s ease-out;
    }
    @keyframes fadeIn {
      from { transform: scale(0.97); opacity: 0; }
      to { transform: scale(1); opacity: 1; }
    }
    .modal-header {
      padding: 1.25rem 1.5rem;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .modal-header h2 {
      font-size: 1.1rem;
      font-weight: 700;
      color: var(--text);
    }
    .modal-close {
      background: none;
      border: none;
      color: var(--text-muted);
      font-size: 1.5rem;
      cursor: pointer;
    }
    .modal-close:hover { color: var(--text); }
    .modal-body {
      padding: 1.5rem;
      overflow-y: auto;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.5rem;
    }
    @media (max-width: 900px) {
      .modal-body { grid-template-columns: 1fr; }
    }
    .modal-section {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }
    .modal-section h3 {
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.25rem;
    }
    .modal-text-box {
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 1rem;
      font-size: 0.85rem;
      white-space: pre-wrap;
      color: var(--text);
      line-height: 1.6;
      max-height: 380px;
      overflow-y: auto;
    }
    /* Simulated Conversation Chat Logs */
    .convo-container {
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      padding: 0.5rem;
      max-height: 380px;
      overflow-y: auto;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 6px;
    }
    .chat-bubble {
      max-width: 85%;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      font-size: 0.82rem;
      line-height: 1.5;
    }
    .bubble-customer {
      background: var(--surface-active);
      color: var(--text);
      align-self: flex-start;
      border-bottom-left-radius: 2px;
    }
    .bubble-support {
      background: var(--accent-muted);
      border: 1px solid var(--accent);
      color: var(--text);
      align-self: flex-end;
      border-bottom-right-radius: 2px;
    }
    .bubble-role {
      font-size: 0.65rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 0.25rem;
      color: var(--text-muted);
    }
  </style>
</head>
<body>

<div class="header">
  <h1>Hiver AI Email Eval — Full Report</h1>
  <div class="subtitle">Generated {timestamp} &nbsp;·&nbsp; Models: {generator_model} (gen) / {grader_model} (eval)</div>
</div>

<div class="container">

  <!-- Top-line Metrics -->
  <div class="section">
    <div class="section-title">Top-Line Metrics</div>
    <div class="metrics-grid">
      <div class="metric-card">
        <div class="label">Total Tickets</div>
        <div class="value accent">{total_tickets}</div>
        <div class="sub">{normal_count} normal · {adv_count} adversarial</div>
      </div>
      <div class="metric-card">
        <div class="label">Abstention Rate</div>
        <div class="value {abst_color}">{abstention_rate}%</div>
        <div class="sub">{abstained_count} abstained (needs human review)</div>
      </div>
      <div class="metric-card">
        <div class="label">Avg Composite Score</div>
        <div class="value {score_color}">{avg_composite}/5</div>
        <div class="sub">across {graded_count} graded replies</div>
      </div>
      <div class="metric-card">
        <div class="label">Resolved Rate</div>
        <div class="value {res_color}">{resolved_rate}%</div>
        <div class="sub">{resolved_count}/{simulated_count} conversations resolved</div>
      </div>
      <div class="metric-card">
        <div class="label">Avg Turns to Resolve</div>
        <div class="value accent2">{avg_turns}</div>
        <div class="sub">across resolved conversations</div>
      </div>
      <div class="metric-card">
        <div class="label">Had to Repeat Ask</div>
        <div class="value {repeat_color}">{repeat_rate}%</div>
        <div class="sub">{repeat_count} of {simulated_count} simulated</div>
      </div>
    </div>
  </div>

  <!-- Adversarial vs Normal -->
  <div class="section">
    <div class="section-title">Adversarial vs. Normal — Score Breakout</div>
    <div class="compare-grid">
      <div class="compare-card normal">
        <h3>✅ Normal Tickets (n={normal_graded})</h3>
        {normal_score_bars}
        <div class="score-row" style="margin-top:1rem; border-top: 1px solid var(--border); padding-top: 0.75rem;">
          <span class="dim" style="font-weight:600;">Composite</span>
          <span style="font-size:1.2rem; font-weight:700; color: var(--accent2);">{normal_composite}/5</span>
        </div>
      </div>
      <div class="compare-card adversarial">
        <h3>🔴 Adversarial Tickets (n={adv_graded})</h3>
        {adv_score_bars}
        <div class="score-row" style="margin-top:1rem; border-top: 1px solid var(--border); padding-top: 0.75rem;">
          <span class="dim" style="font-weight:600;">Composite</span>
          <span style="font-size:1.2rem; font-weight:700; color: var(--accent3);">{adv_composite}/5</span>
        </div>
      </div>
    </div>
  </div>

  <!-- Abstention Breakout -->
  <div class="section">
    <div class="section-title">Abstention Rate Breakout</div>
    <div class="abst-bar">
      {abstention_bars}
    </div>
  </div>

  <!-- Failure Mode Frequency -->
  <div class="section">
    <div class="section-title">Failure Mode Frequency (low-scoring replies only)</div>
    <div class="failure-table">
      <table>
        <thead>
          <tr>
            <th>Failure Mode</th>
            <th>Count</th>
            <th>% of Low-Scoring</th>
            <th>Visual</th>
          </tr>
        </thead>
        <tbody>
          {failure_rows}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Main Table -->
  <div class="section">
    <div class="section-title">Full Ticket Table</div>
    <div class="table-controls">
      <input class="search-box" type="text" id="searchBox" placeholder="Search tickets, categories, messages..." onkeyup="filterTable()">
      <button class="filter-btn active" id="btn-all" onclick="setFilter('all')">All</button>
      <button class="filter-btn" id="btn-normal" onclick="setFilter('normal')">Normal only</button>
      <button class="filter-btn" id="btn-adversarial" onclick="setFilter('adversarial')">Adversarial only</button>
      <button class="filter-btn" id="btn-abstained" onclick="setFilter('abstained')">Abstained</button>
      <button class="filter-btn" id="btn-low" onclick="setFilter('low')">Low scoring (&lt;3)</button>
    </div>
    <div class="main-table-wrapper">
      <div class="table-scroll">
        <table class="main" id="mainTable">
          <thead>
            <tr>
              <th onclick="sortTable(0)">ID ↕</th>
              <th onclick="sortTable(1)">Category ↕</th>
              <th>Mood</th>
              <th>Type</th>
              <th>Customer Message</th>
              <th>AI Reply</th>
              <th onclick="sortTable(6)">Conf ↕</th>
              <th onclick="sortTable(7)">FG ↕</th>
              <th onclick="sortTable(8)">TM ↕</th>
              <th onclick="sortTable(9)">RC ↕</th>
              <th onclick="sortTable(10)">Con ↕</th>
              <th onclick="sortTable(11)">Score ↕</th>
              <th>Failure Mode</th>
              <th>Outcome</th>
              <th>Turns</th>
              <th>Repeated?</th>
            </tr>
          </thead>
          <tbody id="tableBody">
            {table_rows}
          </tbody>
        </table>
      </div>
    </div>
  </div>

</div>

<!-- Modal Dialog -->
<div class="modal-backdrop" id="emailModal" onclick="closeModalOnBackdrop(event)">
  <div class="modal-content">
    <div class="modal-header">
      <h2 id="modalTitle">Ticket Details</h2>
      <button class="modal-close" onclick="closeModal()">&times;</button>
    </div>
    <div class="modal-body">
      <div style="display:flex; flex-direction:column; gap:1.25rem;">
        <div class="modal-section">
          <h3>First Customer Message</h3>
          <div class="modal-text-box" id="modalCustomerMsg"></div>
        </div>
        <div class="modal-section">
          <h3>First AI Generated Draft</h3>
          <div class="modal-text-box" id="modalAiReply"></div>
        </div>
      </div>
      <div class="modal-section">
        <h3>Simulated Multi-Turn Conversation Log</h3>
        <div class="convo-container" id="modalChatHistory"></div>
      </div>
    </div>
  </div>
</div>

<div class="footer">
  Hiver Open Challenge · AI Email Reply Generator + Evaluation System · {timestamp}
</div>

<script>
let currentFilter = 'all';

function filterTable() {
  const query = document.getElementById('searchBox').value.toLowerCase();
  const rows = document.querySelectorAll('#tableBody tr');
  rows.forEach(row => {
    const text = row.textContent.toLowerCase();
    const matchSearch = !query || text.includes(query);
    let matchFilter = true;
    if (currentFilter === 'normal') matchFilter = row.dataset.type !== 'adversarial' && row.dataset.abstained !== 'true';
    else if (currentFilter === 'adversarial') matchFilter = row.dataset.type === 'adversarial';
    else if (currentFilter === 'abstained') matchFilter = row.dataset.abstained === 'true';
    else if (currentFilter === 'low') matchFilter = row.dataset.lowscore === 'true';
    row.style.display = (matchSearch && matchFilter) ? '' : 'none';
  });
}

function setFilter(f) {
  currentFilter = f;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('btn-' + f).classList.add('active');
  filterTable();
}

let sortDir = {};
function sortTable(col) {
  const tbody = document.getElementById('tableBody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  sortDir[col] = !sortDir[col];
  rows.sort((a, b) => {
    const aText = a.cells[col]?.textContent.trim() || '';
    const bText = b.cells[col]?.textContent.trim() || '';
    const aNum = parseFloat(aText);
    const bNum = parseFloat(bText);
    if (!isNaN(aNum) && !isNaN(bNum)) return sortDir[col] ? aNum - bNum : bNum - aNum;
    return sortDir[col] ? aText.localeCompare(bText) : bText.localeCompare(aText);
  });
  rows.forEach(r => tbody.appendChild(r));
}

// Modal Functions
function showModal(ticketId, metaInfo, customerMsg, aiReply, convoJsonStr) {
  document.getElementById('modalTitle').textContent = `Ticket ${ticketId} [${metaInfo}]`;
  document.getElementById('modalCustomerMsg').textContent = customerMsg;
  document.getElementById('modalAiReply').textContent = aiReply;
  
  const chatContainer = document.getElementById('modalChatHistory');
  chatContainer.innerHTML = '';
  
  try {
    const convo = JSON.parse(convoJsonStr || '[]');
    if (convo.length === 0) {
      chatContainer.innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem;padding:1rem;text-align:center;">No simulated turns generated for this ticket (abstained or single-turn).</div>';
    } else {
      convo.forEach(turn => {
        const isSupport = turn.role === 'support' || turn.role === 'agent';
        const bubble = document.createElement('div');
        bubble.className = 'chat-bubble ' + (isSupport ? 'bubble-support' : 'bubble-customer');
        
        const roleDiv = document.createElement('div');
        roleDiv.className = 'bubble-role';
        roleDiv.textContent = isSupport ? 'AI Support Agent' : 'Simulated Customer';
        
        const textDiv = document.createElement('div');
        textDiv.textContent = turn.text || turn.content || '';
        
        bubble.appendChild(roleDiv);
        bubble.appendChild(textDiv);
        chatContainer.appendChild(bubble);
      });
    }
  } catch (e) {
    chatContainer.innerHTML = '<div style="color:var(--red);font-size:0.8rem;padding:1rem;">Failed to parse simulated conversation log.</div>';
  }
  
  document.getElementById('emailModal').style.display = 'flex';
}

function closeModal() {
  document.getElementById('emailModal').style.display = 'none';
}

function closeModalOnBackdrop(event) {
  if (event.target === document.getElementById('emailModal')) {
    closeModal();
  }
}

document.addEventListener('keydown', function(event) {
  if (event.key === 'Escape') {
    closeModal();
  }
});
</script>

</body>
</html>"""


def score_color(val: float | None) -> str:
    if val is None:
        return "accent"
    if val >= 4.0:
        return "good"
    if val >= 3.0:
        return "warn"
    return "bad"


def score_chip(val: int | None) -> str:
    if val is None:
        return "<span style='color:var(--text-muted)'>—</span>"
    cls = f"sc-{min(5, max(1, int(val)))}"
    return f'<span class="score-chip {cls}">{val}</span>'


def score_bar_html(label: str, val: float, color: str = "#6c63ff") -> str:
    pct = val / 5 * 100
    return f"""
    <div class="score-row">
      <span class="dim">{label}</span>
      <div class="score-bar"><div class="score-bar-fill" style="width:{pct:.0f}%;background:{color};"></div></div>
      <span class="score-val">{val:.1f}</span>
    </div>"""


def outcome_badge(outcome: str) -> str:
    mapping = {
        "resolved": ("ob-resolved", "✓ Resolved"),
        "partially_resolved": ("ob-partial", "~ Partial"),
        "not_resolved": ("ob-not", "✗ Not Resolved"),
        "abstained": ("ob-abstained", "⚠ Abstained"),
    }
    cls, label = mapping.get(outcome, ("ob-abstained", outcome))
    return f'<span class="outcome-badge {cls}">{label}</span>'


def failure_tag(fm: str | None) -> str:
    if not fm:
        return "<span style='color:var(--text-muted)'>—</span>"
    tag_map = {
        "hallucinated_policy": "tag-red",
        "wrong_tone": "tag-orange",
        "ignored_question": "tag-yellow",
        "too_long": "tag-purple",
    }
    cls = next((v for k, v in tag_map.items() if fm.startswith(k)), "tag-gray")
    return f'<span class="tag {cls}">{fm}</span>'


def adv_type_tag(adv_type: str | None, is_adv: bool) -> str:
    if not is_adv:
        return '<span class="tag tag-green">normal</span>'
    type_map = {
        "false_claim": "tag-red",
        "hostile_tone": "tag-orange",
        "broken_english": "tag-yellow",
        "policy_violation_request": "tag-purple",
    }
    cls = type_map.get(adv_type or "", "tag-gray")
    return f'<span class="tag {cls}">{adv_type or "adversarial"}</span>'


def conf_badge(conf: str | None) -> str:
    if not conf:
        return "—"
    cls = {"high": "cb-high", "medium": "cb-medium", "low": "cb-low"}.get(conf, "")
    return f'<span class="conf-badge {cls}">{conf}</span>'


def build_html_report(
    replies: list[dict],
    scores: list[dict],
    simulations: list[dict],
) -> str:
    from datetime import datetime
    import os

    generator_model = os.getenv("GENERATOR_MODEL", "gemini-3.5-flash")
    grader_model = os.getenv("GRADER_MODEL", "gemini-3.1-pro-preview")

    # Index by ticket_id
    score_map = {r["ticket_id"]: r for r in scores}
    sim_map = {r["ticket_id"]: r for r in simulations}

    # Top-line metrics
    total = len(replies)
    abstained = [r for r in replies if r.get("abstain")]
    graded = [s for s in scores if not s.get("skipped")]
    simulated = [s for s in simulations if not s.get("skipped")]
    normal = [r for r in replies if not r.get("is_adversarial")]
    adv = [r for r in replies if r.get("is_adversarial")]
    abstention_rate = round(len(abstained) / total * 100, 1) if total else 0

    composites = [s["composite"] for s in graded if s.get("composite") is not None]
    avg_composite = round(sum(composites) / len(composites), 2) if composites else 0

    resolved = [s for s in simulated if s.get("outcome") == "resolved"]
    resolved_rate = round(len(resolved) / len(simulated) * 100, 1) if simulated else 0
    avg_turns = round(
        sum(s.get("turns_to_resolve", 1) for s in resolved) / len(resolved), 1
    ) if resolved else 0
    repeated = [s for s in simulated if s.get("had_to_repeat_ask")]
    repeat_rate = round(len(repeated) / len(simulated) * 100, 1) if simulated else 0

    # Normal vs adversarial scores
    dims = ["factual_grounding", "tone_match", "resolution_completeness", "conciseness"]
    dim_labels = {"factual_grounding": "Factual Grounding", "tone_match": "Tone Match",
                  "resolution_completeness": "Resolution", "conciseness": "Conciseness"}

    def dim_avg(score_list, dim):
        vals = [s["scores"][dim] for s in score_list if s.get("scores") and dim in s["scores"]]
        return round(sum(vals) / len(vals), 1) if vals else 0.0

    normal_scored = [score_map[r["ticket_id"]] for r in normal if r["ticket_id"] in score_map and not score_map[r["ticket_id"]].get("skipped")]
    adv_scored = [score_map[r["ticket_id"]] for r in adv if r["ticket_id"] in score_map and not score_map[r["ticket_id"]].get("skipped")]

    normal_composite = round(
        sum(s["composite"] for s in normal_scored if s.get("composite") is not None) / max(len(normal_scored), 1), 2
    )
    adv_composite = round(
        sum(s["composite"] for s in adv_scored if s.get("composite") is not None) / max(len(adv_scored), 1), 2
    )

    normal_bars = "".join(
        score_bar_html(dim_labels[d], dim_avg(normal_scored, d), "#00d4aa") for d in dims
    )
    adv_bars = "".join(
        score_bar_html(dim_labels[d], dim_avg(adv_scored, d), "#ff6b6b") for d in dims
    )

    # Abstention bars
    adv_abst = [r for r in adv if r.get("abstain")]
    normal_abst = [r for r in normal if r.get("abstain")]
    pv_tickets = [r for r in adv if r.get("adversarial_type") == "policy_violation_request"]
    pv_abst = [r for r in pv_tickets if r.get("abstain")]

    def abst_bar_row(label: str, count: int, total_n: int, color: str) -> str:
        rate = count / total_n * 100 if total_n else 0
        return f"""
        <div class="abst-row">
          <span class="abst-label">{label}</span>
          <div class="abst-track"><div class="abst-fill" style="width:{rate:.0f}%;background:{color};"></div></div>
          <span class="abst-val" style="color:{color};">{rate:.0f}% ({count}/{total_n})</span>
        </div>"""

    abstention_bars = (
        abst_bar_row("All tickets", len(abstained), total, "#6c63ff") +
        abst_bar_row("Normal tickets", len(normal_abst), max(len(normal), 1), "#00d4aa") +
        abst_bar_row("Adversarial tickets", len(adv_abst), max(len(adv), 1), "#ff6b6b") +
        abst_bar_row("policy_violation_request", len(pv_abst), max(len(pv_tickets), 1), "#f59e0b")
    )

    # Failure modes
    failure_counts: dict[str, int] = {}
    low_scoring = [s for s in graded if s.get("composite", 5) < 3.0]
    for s in graded:
        fm = s.get("failure_mode")
        if fm:
            failure_counts[fm] = failure_counts.get(fm, 0) + 1

    failure_rows_html = ""
    if failure_counts:
        total_low = max(sum(failure_counts.values()), 1)
        for fm, cnt in sorted(failure_counts.items(), key=lambda x: -x[1]):
            pct = round(cnt / total_low * 100, 1)
            bar_pct = pct
            failure_rows_html += f"""
            <tr>
              <td>{failure_tag(fm)}</td>
              <td><strong>{cnt}</strong></td>
              <td>{pct}%</td>
              <td><div style="height:8px;width:{bar_pct:.0f}%;max-width:200px;background:#6c63ff;border-radius:4px;opacity:0.7;"></div></td>
            </tr>"""
    else:
        failure_rows_html = "<tr><td colspan='4' style='color:var(--text-muted);text-align:center;padding:2rem;'>No low-scoring replies — no failure modes triggered.</td></tr>"

    # Main table rows
    table_rows_html = ""
    for reply in replies:
        tid = reply["ticket_id"]
        score_rec = score_map.get(tid, {})
        sim_rec = sim_map.get(tid, {})

        is_adv = reply.get("is_adversarial", False)
        is_abstained = reply.get("abstain", False)
        scores_obj = score_rec.get("scores") or {}
        composite = score_rec.get("composite")
        is_low = composite is not None and composite < 3.0
        outcome = sim_rec.get("outcome", "abstained" if is_abstained else "—")

        row_class = " ".join(filter(None, [
            "adversarial" if is_adv else "",
            "abstained" if is_abstained else "",
        ]))

        msg_truncated = (reply.get("customer_msg", "") or "")[:120].replace('"', '&quot;')
        full_msg = (reply.get("customer_msg", "") or "").replace('"', '&quot;')
        reply_truncated = (reply.get("reply_text", "") or "")[:120].replace('"', '&quot;')
        full_reply = (reply.get("reply_text", "") or "").replace('"', '&quot;')

        fg = scores_obj.get("factual_grounding")
        tm = scores_obj.get("tone_match")
        rc = scores_obj.get("resolution_completeness")
        co = scores_obj.get("conciseness")

        turns_val = sim_rec.get("turns_to_resolve", "—")
        had_repeat = sim_rec.get("had_to_repeat_ask")
        repeat_str = ("Yes" if had_repeat else "No") if had_repeat is not None and not is_abstained else "—"

        meta_info = f"{reply.get('category','').title()} — {reply.get('mood','').title()}"
        meta_info_esc = meta_info.replace("'", "\\'")
        msg_esc = full_msg.replace("'", "\\'")
        reply_esc = full_reply.replace("'", "\\'")

        convo_list = sim_rec.get("conversation", [])
        convo_json_esc = json.dumps(convo_list).replace("'", "\\'").replace('"', '&quot;')

        table_rows_html += f"""
        <tr class="{row_class}" 
            data-type="{'adversarial' if is_adv else 'normal'}"
            data-abstained="{'true' if is_abstained else 'false'}"
            data-lowscore="{'true' if is_low else 'false'}">
          <td><code style="font-size:0.75rem;">{tid}</code></td>
          <td><span class="tag tag-blue">{reply.get('category','')}</span></td>
          <td style="font-size:0.8rem;color:var(--text-muted);">{reply.get('mood','')}</td>
          <td>{adv_type_tag(reply.get('adversarial_type'), is_adv)}</td>
          <td>
            <div class="msg-cell-content">
              <span class="msg-text-truncated">{full_msg[:50]}...</span>
              <button class="btn-read-more" onclick="showModal('{tid}', '{meta_info_esc}', '{msg_esc}', '{reply_esc}', '{convo_json_esc}')">Read</button>
            </div>
          </td>
          <td>
            <div class="msg-cell-content">
              <span class="msg-text-truncated">{full_reply[:50]}...</span>
              <button class="btn-read-more" onclick="showModal('{tid}', '{meta_info_esc}', '{msg_esc}', '{reply_esc}', '{convo_json_esc}')">Read</button>
            </div>
          </td>
          <td>{conf_badge(reply.get('confidence'))}</td>
          <td>{score_chip(fg)}</td>
          <td>{score_chip(tm)}</td>
          <td>{score_chip(rc)}</td>
          <td>{score_chip(co)}</td>
          <td><span style="font-weight:700;color:{'var(--green)' if composite and composite>=4 else 'var(--yellow)' if composite and composite>=3 else 'var(--red)' if composite else 'var(--text-muted)'}">
            {f'{composite:.1f}' if composite else ('—' if is_abstained else '—')}
          </span></td>
          <td>{failure_tag(score_rec.get('failure_mode'))}</td>
          <td>{outcome_badge(outcome)}</td>
          <td style="text-align:center;">{turns_val}</td>
          <td style="text-align:center;color:{'var(--red)' if had_repeat else 'var(--green)' if had_repeat is False and not is_abstained else 'var(--text-muted)'};">{repeat_str}</td>
        </tr>"""

    return HTML_TEMPLATE.format(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        generator_model=generator_model,
        grader_model=grader_model,
        total_tickets=total,
        normal_count=len(normal),
        adv_count=len(adv),
        abstention_rate=abstention_rate,
        abst_color=score_color(5 - abstention_rate / 10),
        abstained_count=len(abstained),
        avg_composite=avg_composite,
        score_color=score_color(avg_composite),
        graded_count=len(graded),
        resolved_rate=resolved_rate,
        res_color="good" if resolved_rate >= 70 else "warn" if resolved_rate >= 50 else "bad",
        resolved_count=len(resolved),
        simulated_count=len(simulated),
        avg_turns=avg_turns,
        repeat_rate=repeat_rate,
        repeat_color="bad" if repeat_rate > 30 else "warn" if repeat_rate > 15 else "good",
        repeat_count=len(repeated),
        normal_graded=len(normal_scored),
        adv_graded=len(adv_scored),
        normal_score_bars=normal_bars,
        adv_score_bars=adv_bars,
        normal_composite=normal_composite,
        adv_composite=adv_composite,
        abstention_bars=abstention_bars,
        failure_rows=failure_rows_html,
        table_rows=table_rows_html,
    )


# ── Main orchestrator ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run the full Hiver AI eval pipeline.")
    parser.add_argument("--skip-dataset", action="store_true", help="Skip dataset generation")
    parser.add_argument("--skip-replies", action="store_true", help="Skip reply generation")
    parser.add_argument("--report-only", action="store_true", help="Only regenerate report")
    args = parser.parse_args()

    os.makedirs(RESULTS_DIR, exist_ok=True)
    start_total = time.time()

    print("\n" + "="*60)
    print("  Hiver AI Email Eval — Full Pipeline")
    print("="*60)

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key.strip() in ("", "YOUR_GOOGLE_API_KEY", "PLACEHOLDER_KEY", "PLACEHOLDER"):
        print("\n[INFO] GOOGLE_API_KEY is not configured in .env.")
        print("  → Running in mock/offline mode (generating report from seed_data.py)...")
        import importlib.util
        seed_spec = importlib.util.spec_from_file_location("seed_data", os.path.join(BASE_DIR, "seed_data.py"))
        seed_module = importlib.util.module_from_spec(seed_spec)
        seed_spec.loader.exec_module(seed_module)
        seed_module.main()
        sys.exit(0)

    if not args.report_only:

        # Step 1: Dataset
        if not args.skip_dataset and not args.skip_replies:
            ok = run_step(
                os.path.join(BASE_DIR, "data", "generate_dataset.py"),
                "Generate Dataset",
            )
            if not ok:
                print("Pipeline stopped at dataset generation.")
                sys.exit(1)
        else:
            print("\n[SKIP] Dataset generation")

        # Step 2: Replies
        if not args.skip_replies:
            ok = run_step(
                os.path.join(BASE_DIR, "generator", "generate_replies.py"),
                "Generate Replies",
            )
            if not ok:
                print("Pipeline stopped at reply generation.")
                sys.exit(1)
        else:
            print("\n[SKIP] Reply generation")

        # Step 3: Rubric grading
        ok = run_step(
            os.path.join(BASE_DIR, "eval", "rubric_grader.py"),
            "Rubric Grader",
        )
        if not ok:
            print("Pipeline stopped at rubric grading.")
            sys.exit(1)

        # Step 4: Customer simulation
        ok = run_step(
            os.path.join(BASE_DIR, "eval", "customer_simulator.py"),
            "Customer Simulator",
        )
        if not ok:
            print("Pipeline stopped at customer simulation.")
            sys.exit(1)

    # Step 5: Build HTML report
    print(f"\n{'='*60}")
    print("  STEP: Building HTML Report")
    print("="*60)

    replies = load_jsonl(os.path.join(RESULTS_DIR, "replies.jsonl"))
    scores = load_jsonl(os.path.join(RESULTS_DIR, "scores.jsonl"))
    simulations = load_jsonl(os.path.join(RESULTS_DIR, "simulation.jsonl"))

    if not replies:
        print("ERROR: results/replies.jsonl is empty or missing.")
        sys.exit(1)

    html = build_html_report(replies, scores, simulations)
    report_path = os.path.join(RESULTS_DIR, "report.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  ✓ Report written to {report_path}")

    # Step 6: Calibration (optional — only if gold set has human scores)
    gold_path = os.path.join(BASE_DIR, "gold", "gold.jsonl")
    if os.path.exists(gold_path):
        gold_records = load_jsonl(gold_path)
        has_scores = any(r.get("human_score") is not None for r in gold_records)
        if has_scores:
            ok = run_step(
                os.path.join(BASE_DIR, "eval", "calibration.py"),
                "Calibration (Gold Set)",
            )
        else:
            print(
                "\n[SKIP] Calibration — gold/gold.jsonl has no human_score values yet.\n"
                "  → Fill in human_score (1-5) for tickets in gold/gold.jsonl and re-run."
            )

    elapsed = time.time() - start_total
    print(f"\n{'='*60}")
    print(f"  ✅ Pipeline complete in {elapsed:.1f}s")
    print(f"{'='*60}")
    print(f"\n  Results:")
    print(f"    results/replies.jsonl")
    print(f"    results/scores.jsonl")
    print(f"    results/simulation.jsonl")
    print(f"    results/report.html        ← open in browser")
    print(f"    results/calibration_report.md")
    print()


if __name__ == "__main__":
    main()
