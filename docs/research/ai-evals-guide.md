# AI Evals Guide

*Source: Applied AI Evals — https://evals.info*

---

## 1. How To Do Error Analysis

Error Analysis allows you to quickly find patterns of failures in your AI product's logs (traces).

1. **Collect Traces**: Gather a diverse sample of 100+ traces from production or your own real/synthetic usage.
2. **Annotate Traces** ("aka Open Coding"): Review each trace and write brief, unstructured notes on the problem (e.g., "hallucinated a fact", "misused the user's name", "failed to use the calculator tool").
3. **Group & Categorize**: Group similar notes into clusters (e.g., tone violations, failed tool calls).
4. **Prioritize**: Count the frequency of each category, which informs your priority.

Keep looking at data until you feel like you aren't learning anything new. This is called **"theoretical saturation"**.

**Process flow:**

```
Add New Traces         Read And Open
(Real or Synthetic) →  Code Traces
      ↑                     ↓
Re-Code Traces         Axial Coding:
With Failure Modes  ←  Refine Failure Modes
```

> **Theoretical saturation:** Repeat until no new failure modes & no changes in re-coding appear.

As a rule of thumb, you need **~100 high-quality, diverse traces**. Those can be real data, synthetic data, or both — coded with pass/fail and failure modes.

---

## 2. When To Write An Eval

*(But you don't always need to)*

```
Have you observed the failure w/ error analysis?
├── No  → STAY AWAY
│         Do error analysis first. Your evals should
│         target errors you observe or induce.
│
└── Yes → How much iteration is required to fix?
          ├── Little → UNCLEAR VALUE
          │             Can an inexpensive eval like a code
          │             based assertion work?
          │             Does it make sense to just fix
          │             and move on?
          │
          └── Lots  → HIGH VALUE
                       Evals are most valuable here.
                       Expensive evals like a LLM-as-a-
                       judge might be feasible.
```

> **Note:** Evals provide more value when you need to hill climb against an error.

---

## 3. Don't Use Generic Eval Metrics

**Don't use (Generic Scores):**
- Rouge
- Bleu
- Faithfulness
- Helpfulness
- Tone

**Do use (Application-Specific Metrics):**
- Calendar Scheduling Failure
- Interrupted Conversation Flow
- Widget Rendering Issue
- Email recipient incorrect
- Failure to Escalate to Human

### Good eval metrics:

- Measure an **error you've observed**.
- Relates to a **non-trivial issue** you will iterate on.
- Are scoped to a **specific failure**.
- Has a **binary outcome** (not 1-5 score).
- Is **verifiable** (i.e., human labels for LLM-as-a-Judge).

> *The checklist helps you obtain positive ROI from evals (since they aren't free). More details: [hamel.dev/evals-faq](https://hamel.dev/evals-faq)*

---

## 4. Don't Make These Common AI Eval Mistakes

1. **Not looking at your data first.** An automated eval is useless if it doesn't measure your specific failures. The best way to find these is to look at your data first. Off-the-shelf metrics like "helpfulness score" are a bad idea for this reason.

2. **Not validating your LLM Judge.** When using a LLM Judge, you must measure the judge against a human label. Not doing so creates an untrustworthy and misaligned metric.

3. **Saturated evals.** AI evals are most valuable when they find new failures. A perfect score (100%) on all evals often means they are saturated or too easy. Add hard test cases to keep guiding improvement.

---

## 5. Types of Automated Evals

### 1. Code-Based Assertions
Check for objective, rule-based failures. Ex: matching keywords, confirming tool execution, etc. Use these wherever possible, as they are **fast, cheap, deterministic, and interpretable**.

### 2. LLM-as-a-Judge
Uses a LLM to assess subjective or nuanced criteria that isn't suitable for code. While powerful, they are **slower, more expensive, and require verification and alignment**. Reserve these for important failures as they aren't free.

### 3. Guardrails
Run in the request/response path to block failures before they reach the user. These tend to be fast and have a low false positive rate to avoid blocking valid responses. These are **commonly code-based checks or small classifiers**.

---

## 6. Don't Use Likert Scales (1-5) for LLM-As-A-Judge

Binary (pass/fail) scores are usually preferable to Likert scales (1-5 ratings).

**Why not Likert?**
- Likert scales are expensive to align with domain experts.
- Annotators often default to middle values to avoid making difficult decisions.
- They can encourage too much scope (an overall quality score vs. a targeted eval).

**Why binary?**
- Binary scores compel the annotator to make a definitive decision.
- Better aligns with the reality that you must decide whether or not the AI feature is good enough to ship.
- Binary scores are also easier to apply during error analysis.

**Don't do this:**

```
LLM Output → Likert Scale Judge → Score: 3/5   ✗
```

**Do this:**

```
LLM Output → is_polite      → ✓ Pass
           → scheduling     → ✗ Fail    → Actionable Evals
           → human_handoff  → ✓ Pass
```

---

## 7. How To Trust A LLM Judge

The **only** way to trust a LLM Judge is to measure it against human labels.

Split your human labeled data into 3 sets:

| Set       | % of Examples | Purpose                                              |
|-----------|---------------|------------------------------------------------------|
| **Train** | ~20%          | Draw your few-shot examples from here                |
| **Dev**   | ~40%          | Use to optimize your judge                           |
| **Test**  | ~40%          | Final check to make sure you haven't overfit         |

**Don't report "accuracy"** — it's misleading on imbalanced data. Use True Positive Rate (TPR) and True Negative Rate (TNR).

**Aim for a high TPR & TNR (e.g., > 90%)**

```
TPR = True Positive / (True Positive + False Negative)
TNR = True Negative / (True Negative + False Positive)
```

> *The sets are different from ML because we aren't "training" anything. We are just using data to inform the judge's prompt.*

---

## 8. Ways to Sample Traces for AI Evals

### Explore

- **Random**: Always do this alongside other strategies to discover unknown issues.
- **Clustering**: Group traces according to semantic similarity or clustering algorithm & see if you discover new errors.
- **Data Analysis**: Analyze statistics on latency, turns, tool calls, tokens, etc. for outliers.
- **Classification**: Use your existing evals, a predictive model, or a LLM to surface problematic traces. Do this with caution.

### Use Signals

- **Feedback**: Use explicit customer feedback to filter traces.

---

## 9. Tips on Generating Synthetic Data for Bootstrapping Evals

- **Use structured input for diversity.** Define key dimensions (e.g., Feature, Persona, Scenario) and use them as variables in your prompt.

- **Seed with real data.** When possible, seed your generation with real logs or traces. Then, ask the model to explicitly inject changes, like a new constraint or a modified variable, to create realistic edge cases.

- **Enforce output structure & filter.** Define a schema for the output. Generate many candidates, then filter to retain the highest-quality, challenging examples.

- **Increase complexity iteratively.** Start with simple queries and incrementally ask the LLM to add constraints, complex formatting, etc.

- **Don't** prompt with zero-shot requests lacking structured input. Example: "Generate 50 test cases". These tend to yield generic, repetitive inputs.

---

## 10. How to Read and Use Traces for Evals

1. **Start with error analysis.** When reviewing traces, stop at the first (most upstream) error you find. This keeps things tractable — upstream failures tend to be more important.

2. **Gather and minimally reproduce.** Gather traces related to your top failures. For each of these traces, **minimally reproduce the failure** in as few turns with as least amount of complexity possible.

3. **N=1: Collect a dataset.** Collect a dataset of minimally reproduced error traces and use the N=1 turns before the error as test cases. This assumes your system isn't changing rapidly.

4. **Advanced: Modified traces.** For additional test coverage, you can modify traces from #3 in valid ways (rephrasing the user question, etc.) with a LLM.

5. **Advanced — Simulate a user** with another LLM. Doing this well can be challenging.

---

## 11. How to Use a Transition Matrix to Find Errors

When you have an agent with many steps (e.g., Plan, Search, Code, Finalize), it's hard to know which step is failing most. A **Transition Failure Matrix** helps you find the hotspots.

### How it works:

1. **Define states**: List all the possible steps or "states" your agent can be in.
2. **Create a matrix**: Create a grid where the rows are the "From" state and the columns are the "To" state.
3. **Count failures**: For each failure, identify the last successful transition that happened before the error. Populate the count of failures in the grid cells accordingly.

### Example: Failure Occurred In State

|              | PlanA | SearchB | GenCodeC | TestRunD | FixCodeE | PlanA2 | CodeF |
|--------------|-------|---------|----------|----------|----------|--------|-------|
| **PlanA**    |       | 7       | 1        |          |          |        |       |
| **SearchB**  |       |         | 8        |          |          |        |       |
| **GenCodeC** |       |         |          | 2        |          |        |       |
| **TestRunD** |       |         |          |          | 6        |        |       |
| **FixCodeE** |       |         |          | 0        |          | 3      |       |
| **PlanA2**   |       |         |          |          |          |        | 2     |

> *See Bryan Bischof's related talk: https://bit.ly/failure-matrix*

---

## 12. How to Deploy Evals for Continuous Evaluation

|                          | CI/CD                    | Online Monitoring                       | Guardrails                                     |
|--------------------------|--------------------------|-----------------------------------------|------------------------------------------------|
| **What's the goal?**     | Prevent regressions      | Discover new failures & track performance | Enforce safety & block high-impact errors      |
| **When do I do this?**   | Pre-merge (pull request) | Async (post-response)                   | Synchronous (pre-response)                     |
| **How do I do this?**    | Unit tests, LLM-judge    | Unit tests, LLM-judge, A/B testing      | Unit tests, small classifiers                  |
| **What data do I use?**  | Curated test cases       | Sampled production traffic              | 100% of live traffic                           |
| **What do I do on failure?** | Block merge          | Trigger an alert                        | Block response, retry, or fallback to alternative |
