# Pin: Microsoft Trace as a Possible Skeleton

**Repo:** [microsoft/Trace](https://github.com/microsoft/Trace) — *End-to-end Generative Optimization for AI Agents*

**TL;DR:** Yes, Trace can help. It gives a ready-made skeleton: computation graph over LLM calls, trainable prompt-like parameters, feedback functions (numeric + text), and a training loop with pluggable optimizers. We’d use it for the “run agent → get feedback → update prompt” loop and add our document ingestion, metric, and eval set on top.

---

## What Trace Is

- **PyTorch-like library** for optimizing AI systems with general feedback (rewards, losses, natural language, compiler errors, etc.).
- **Main primitives:**
  - **`node`** — a value in the computation graph; can be marked `trainable=True` so the optimizer updates it (e.g. prompt text).
  - **`bundle`** — a function (e.g. Python or LLM call) that can be optimized; decorator `@bundle(trainable=True)`.
- **Execution is traced** automatically; the optimizer uses the trace + feedback to propose updates.
- **Optimizers:** OptoPrime (their default, 2–3× faster than TextGrad), TextGrad, OPRO. All work with the same graph + feedback interface.
- **LLM backend:** LiteLLM or AutoGen (API keys, model choice).
- **Docs / tutorials:** [microsoft.github.io/Trace](https://microsoft.github.io/Trace/), Colab notebooks for “Getting Started,” “Adaptive AI Agent,” “NLP Prompt Optimization” (BigBench-Hard), etc.

So Trace already gives: *define graph → define feedback → optimizer.backward(feedback) → optimizer.step()* and the “parameters” that get updated can be prompt strings or instruction nodes.

---

## How It Maps to Our Project

| Our concept | In Trace |
|------------|----------|
| **System prompt (the thing we optimize)** | A `node(...)` or `@bundle` content that is `trainable=True` (e.g. instruction text). |
| **Single run:** document + prompt → LLM → output | One or more `trace.operators.call_llm(system_prompt, instruction_node, user_input)` (or similar) in the graph. |
| **Feedback function µf (score + text)** | The function we pass to the optimizer: e.g. `feedback_fn(model_output, ground_truth)` returning "Correct" / "Incorrect" or richer text. Trace supports natural-language feedback. |
| **Evaluation loop** | `optimizer.zero_feedback()` → run agent (e.g. `agent(doc)`) → `feedback = feedback_fn(...)` → `optimizer.backward(node, feedback)` → `optimizer.step()`. |
| **Document input** | Our code: load PDF → encode (images or OCR) → pass into the graph as a non-trainable input. |

So we don’t have to build the “optimization loop” from scratch; we plug in our document loader, our metric, and our feedback text.

---

## What We’d Use as Skeleton

1. **Graph definition** — One (or a few) trainable nodes for the system prompt / instructions; one or more `call_llm`-style nodes that take (prompt, document_representation).
2. **Feedback function** — Our µf: compare model output to ground truth, return a score and (for Trace) text feedback (e.g. “RO number wrong; VIN missing”). Trace’s optimizers can consume that.
3. **Training loop** — Use Trace’s loop (e.g. OptoPrime or TextGrad) over our eval set or minibatches; `backward` + `step` update the trainable prompt nodes.
4. **Baseline vs optimized** — Run once with initial prompt (no steps / zero steps) to get baseline score; then run the optimizer for N steps and record score again. Delta = prompt-attributable improvement.

We’d add ourselves:

- **Document pipeline** — Load PDF, optionally OCR or render to images, pass into the graph. Not part of Trace.
- **Our metric and µf** — Field-level accuracy, missing/wrong field text, etc. Implement as our Python function, then pass its output as feedback.
- **Eval set and ground truth** — Our Data/Samples and hand-built references; feed them into the feedback function.

---

## How Trace Differs from GEPA (and why both still fit)

- **GEPA** (our reference in the architecture doc): Reflective prompt *evolution* — an LLM *reflects* on trajectories and *rewrites* the prompt; Pareto-based candidate selection; very sample-efficient.
- **Trace**: Optimizer (OptoPrime, TextGrad, OPRO) takes feedback and *updates* graph parameters (e.g. prompt text) via its own internal logic; no separate “reflection LLM” in the loop by default.

So Trace is a **skeleton for the loop and the graph**; the *mechanism* of prompt update is Trace’s optimizer, not GEPA’s reflection. We can still:

- Use Trace to get a working “prompt optimization pipeline” quickly (same model, same data, only prompt parameters change → clear attribution).
- Later, if we want GEPA-style reflection, we could either (a) use GEPA’s code for the optimizer and Trace only for tracing, or (b) compare Trace optimizers vs a GEPA-style reflector in our write-up.

For “show improvement from better prompts,” Trace is enough as a skeleton; we’re not tied to GEPA’s specific update rule.

---

## Practical Next Steps (when we’re ready to build)

1. **Try Trace locally** — `pip install trace-opt`, run the “Getting Started” and “Adaptive AI Agent” tutorials so we see `node`, `bundle`, feedback, and `OptoPrime`.
2. **Minimal document agent in Trace** — One trainable system prompt node, one `call_llm(prompt, document_text_or_image_ref)`, output parsed to fields; feedback = our µf(doc, output, ground_truth).
3. **Connect our data** — Load one of our sample PDFs (or a stub), run the agent, and hook our metric + feedback text into `optimizer.backward(...)`.
4. **Baseline run** — Don’t call `optimizer.step()` (or run 0 epochs); record score. Then run N optimization steps and record again. Report delta.

---

## References

- **Trace repo:** https://github.com/microsoft/Trace  
- **Trace docs:** https://microsoft.github.io/Trace/  
- **Our architecture (prompt-only, fixed model/data):** `ARCHITECTURE_AND_INITIAL_STEPS.md`  
- **Our high-level flow:** `HIGH_LEVEL_OVERVIEW.md`

*Pin created so we don’t lose this option when we move from design to implementation.*
