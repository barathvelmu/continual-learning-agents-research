# continual-learning-agents-research  
BMW Group × MIT GenAI Lab  
Continuous Evaluation & Autonomous Prompt Optimization

---

## Project

We are building a closed-loop system that improves AI agents **without retraining models**. Instead of fine-tuning, we treat the **system prompt as a policy layer** and optimize it using structured evaluation feedback.

Loop:

Evaluate → Modify Prompt → Re-test → Select Improvement

Goal: enable agents to adapt to evolving tasks in non-stationary production environments.

---

## Scope (MVP)

- Automated prompt optimization loop
- Measurable improvement over baseline
- No model weight updates
- No RL or fine-tuning

For now, proof-of-concept only.

---

## Workflow

**Google Colab**  
Used for compute capability. We use our student accounts.

**GitHub (this repo)**  
Used for:
- Centralized version control  
- Benchmark tracking  
- Team visibility  

Colab = compute + coding  
GitHub = storage + record

---

## Repository Structure
**Data/**  
Evaluation datasets.

**Experimentation/**  
Individual research notebooks.

**Notebooks/**  
Versioned system pipeline iterations. This is what we track and share; the final polished notebooks. 

---

Outcome: a self-evolving prompt optimization pipeline for enterprise agents.
