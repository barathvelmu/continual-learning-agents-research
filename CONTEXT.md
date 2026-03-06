# BMW x MIT GenAI Lab - Research Context
> Centralized reference for Claude Code. Last updated: 2026-03-05.

---

## Project in One Sentence

Build a closed-loop system that improves BMW repair-order interpretation agents **without retraining any model** — by automatically evolving the system prompt using evaluation feedback.

---

## The Core Experiment (What We're Proving)

1. Start with a baseline prompt + an LLM that reads BMW repair-order PDFs
2. Run automated prompt optimization (GEPA-style)
3. Show: **same model, same documents, better prompt → measurably better extraction**

The delta (before vs after prompt optimization) is the entire point. BMW doesn't care about raw accuracy — they care that prompt evolution demonstrably helps.

---

## Pipeline Architecture

```
PDF (repair order)
      |
      v
[FIXED] Document Encoding
  - Option A: Vision model (e.g. GPT-4V, Claude, LLaVA) reads page images
  - Option B: Fixed OCR → text
  (never changes between baseline and optimized runs)
      |
      v
[TRAINABLE] LLM + System Prompt
  - Only the system prompt changes during optimization
  - Outputs structured JSON matching ground-truth schema
      |
      v
[FIXED] Evaluation: eval.py
  - Compares predicted JSON vs ground-truth JSON
  - Returns: score (0-1) + per-field issue text (mu_f)
      |
      v
[OPTIMIZER] GEPA-style Prompt Update
  - Reads: current prompt + execution trace + score + feedback text
  - Reflection LLM proposes a new system prompt
  - Pareto pool keeps best-per-document prompts (avoids local optima)
      |
      v
[LOOP] Update prompt → re-run → repeat
```

Erwin's version (from Notes_04-03-2026):
```
Document Image → Vision Model (LLaVA) → Extracted Text
  → LLM Extraction Agent (Agent Prompt)
  → Structured Output → Evaluation
  → Prompt Optimization Agent (updates prompts)
```

---

## Data

**Location:** `Data/Samples/`

6 sample repair-order documents, each with:
- `{id}.pdf` — the actual repair order (image-based, multi-section)
- `{id}.json` — ground truth structured JSON

**JSON schema structure:**
```json
{
  "doc_id": "201414",
  "sections": [
    {
      "section_id": "ASI-201414",
      "prefix": "ASI",  // section type: ASI, BWO, CSI, JSI, WSI, ISI
      "page_count": 1,
      "header": { "ro_number", "vin", "customer_name", "vehicle", "dates", ... },
      "footer": { "labor_amount", "parts_amount", "total_charges", ... },
      "content": { "job": [...], "labor": [...], "acct_split": [...], ... }
    }
  ]
}
```

Sections vary in schema (ASI is most complete; BWO is minimal). Header fields include: ro_number, vin, customer name/address, vehicle (year/make/model/submodel/color/engine), dates, advisor, miles, financials.

---

## Evaluation (`Scripts/eval.py`)

**This is the official scorer — Jason (BMW) provided the spec.**

Usage:
```bash
python eval.py --gt ground_truth.json --pred prediction.json
python eval.py --gt gt.json --pred pred.json --out report.json
```

Public API: `evaluate_extraction(ground_truth, prediction, config=None) -> dict`

**Scoring rubric (weighted categories):**
| Category  | Weight | What it covers |
|-----------|--------|----------------|
| structure | 45%    | missing/extra keys, wrong types |
| numbers   | 40%    | numeric field accuracy (RO#, VIN, amounts) |
| text      | 15%    | free-text fields |

Returns: `{ score: 0-1, subscores: {...}, issues: [...] }`
Each issue has: category, kind (missing/extra/type/value), path, expected, got, penalty, severity.

This output = the **mu_f feedback function** for GEPA. Score = mu, issues text = feedback.

---

## Key Papers & Notes

### 1. GEPA (ICLR 2026) — PRIMARY APPROACH
- **Paper:** "GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning"
- **Repo:** https://github.com/gepa-ai/gepa
- **Notes:** `Experimentation/Bernardo/GEPA_PAPER_NOTES.tex` + `Literature_and_notes/GEPA_PAPER_NOTES.pdf`
- **Key idea:** Evolve prompts via natural-language reflection on execution traces. Pareto frontier keeps diversity.
- **Results:** 35x fewer rollouts than RL (GRPO), +6% avg over GRPO, +10% over MIPROv2.
- **Why fits us:** Sample-efficient (limited data), no model updates, interpretable prompts, text feedback (mu_f) maps directly.
- **Mapping:**
  - Our compound system = PDF → encoding → LLM(prompt) → JSON
  - Task instance = one document + ground truth
  - Metric mu = eval.py score
  - Feedback mu_f = eval.py score + issue text
  - Pareto = keep prompts that are best on at least one document
  - Rollout budget = how many API calls we can afford

### 2. Trace (NeurIPS 2024) — EXECUTION HARNESS
- **Repo:** https://github.com/microsoft/Trace
- **Notes:** `Literature_and_notes/TRACE_NOTES.pdf`
- **Key idea:** PyTorch-like computation graph for agents. Prompt = trainable node. Traces execution for optimizers.
- **Why fits us:** Gives clean "prompt as updatable object" + execution trace without building it from scratch.
- **Role:** Trace = skeleton (runs agent, stores prompt, captures trace). GEPA = brain (updates prompt from trace).

### 3. Evolutionary Prompt Optimization (ICLR 2025 Workshop) — ALTERNATIVE/COMPLEMENT
- **Paper:** arXiv:2503.23503 (Bharthulwar, Rho, Brown — Harvard)
- **Notes:** `Experimentation/Bernardo/EVOLUTIONARY_PROMPT_OPTIMIZATION_NOTES.tex`
- **Key idea:** Binary tournament selection, LLM-guided mutation. Works for VLMs. Discovers emergent tool use.
- **Fitness:** F = (1-λ)*F_task + λ*F_aux (λ=0.25), where F_aux = LLM critic.
- **Why fits us:** ~20 labeled examples suffice. Alternative to GEPA if we want tournament-based evolution.
- **Emergent finding:** Evolved prompts discover hierarchical document partitioning and tool calls automatically.

### 4. DSPy + MIPROv2 — COMPARISON APPROACH
- **Repo:** https://github.com/stanfordnlp/dspy
- **Key idea:** Bayesian optimization over prompt instruction + few-shot examples.
- **Requires:** 20-50 labeled examples.
- **Trade-off vs GEPA:** Batch learning (needs dataset upfront) vs instance-level reflection. Less diverse handling.

---

## Proposed Framework (Bernardo's Recommendation)

**Stage 1 (Start here):** Simple intake
- Vision model with basic prompt OR fixed OCR
- No optimization of the extraction step
- Keeps pipeline tractable; improvement attributable to agent prompt only

**Stage 2:** Optimization loop (Trace + GEPA)
- Trace execution graph with trainable prompt node
- GEPA reflection: (prompt, trace, score, mu_f_text) → new prompt
- Pareto pool for diversity across document types

**Stage 3 (later):** Full CV active extraction
- Hierarchical partitioning (header/parts table/footer regions)
- Tool-augmented perception (crop/segment blurry areas)
- EPO-style prompt evolution for the vision agent itself

---

## What's Done vs Not Done

### Done
- [x] Literature review + notes (GEPA, Trace, EPO) — Bernardo
- [x] Preliminary Framework doc — Bernardo
- [x] Architecture & initial steps doc — Bernardo
- [x] Pipeline diagram — Erwin
- [x] eval.py evaluation script — Jason (BMW) / team
- [x] 6 sample document pairs (PDF + ground truth JSON)
- [x] README and repo structure

### NOT Done (as of 2026-03-05)
- [ ] Baseline LLM extraction (no code yet)
- [ ] Prompt optimization loop (no code yet)
- [ ] Any actual experiment run (all notebooks are empty/broken)
- [ ] Literature review document for BMW (due March 7)
- [ ] Vision/OCR intake decision (pick one and implement)
- [ ] Barath's notebook — empty

---

## Immediate Next Steps (By March 7 — Literature Review Due)

1. Literature review document for BMW meeting (covers GEPA, Trace, EPO)
2. Pick an intake method (vision model recommendation: Claude or GPT-4V via API in Colab)
3. Write baseline system prompt
4. Implement basic extraction loop in Colab notebook
5. Run eval.py on baseline predictions → get baseline score
6. Implement one iteration of GEPA reflection → show improvement

---

## Repo Structure

```
Data/Samples/            # 6 PDF+JSON document pairs
Experimentation/
  Barath/Barath.ipynb    # empty
  Bernardo/              # all the notes/docs (.tex + .pdf)
  Erwin/                 # pipeline diagram, empty notebook
  Ivy/                   # empty notebook
Literature_and_notes/    # papers (.pdf) + notes (.pdf) + links file
Notebooks/               # versioned shared notebooks (1.0, 1.1, 1.2) — all empty
Scripts/eval.py          # evaluation script (JSON comparison with scoring)
meeting-notes/           # meeting notes
README.md                # project overview
```

---

## Key Decisions / Constraints

- **Compute:** Google Colab only (student accounts). All code must be `.ipynb`.
- **No model training:** Zero weight updates. Prompt-only optimization.
- **Goal is POC:** Not production. If interesting, can become a paper.
- **Evaluator:** `eval.py` is the reference scorer (BMW will use this). Can also build custom evaluators, but must report with this one.
- **Data:** Very limited (6 labeled samples currently). Sample efficiency matters.
- **Timeline:** Already behind. Bernardo + team did all the docs; need actual experiments now.

---

## Barath's Context

- Previously implemented GEPA for AB InBev research (different domain). Has working GEPA knowledge.
- Has done zero work in this repo so far.
- Needs to run in Colab — everything must be `.ipynb` or supporting scripts.
- Good starting point: build a minimal extraction + eval baseline in Colab, then layer on GEPA reflection.
