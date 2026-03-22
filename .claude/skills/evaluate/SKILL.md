---
name: evaluate
description: Evaluate the quality of an agent's answer from a trace file using expert-informed rubrics. Persists results as .eval.json next to the trace.
argument-hint: "[question-slug or workspace/slug]"
allowed-tools: Read, Glob, Grep, Bash, Write
---

Evaluate the quality of an agent's answer from a trace file.

## Find the trace

If `$ARGUMENTS` is provided, find the trace matching that slug in `traces/`. Otherwise, find the most recent trace by file modification time.

Read the trace JSON to extract: question, answer, category, workspace, assertions, tool_calls, and scratchpad_files. Note the trace file path — you will write the eval file next to it.

## Build the rubric

1. **Identify experts.** Name 2-3 well-regarded, widely published experts in the subject area of this workspace. Be specific — real people with real credentials.

2. **Channel their perspective.** Consider how those experts would evaluate an answer to this specific question. What would they look for? What would impress them? What would they flag as superficial or wrong?

3. **Generate rubric dimensions.** Create 4-6 scoring dimensions tailored to the question's category. Always include:
   - **Accuracy** — Are factual claims correct and verifiable from the source material?
   - **Citation quality** — Does the answer cite specific sources (file, row, passage)?

   Add dimensions based on category:
   - `single_fact` / `single_doc`: Completeness, precision
   - `multi_doc` / `enumeration`: Coverage, systematic approach
   - `comparison`: Balance, identification of key differentiators
   - `cross_reference`: Connection quality, non-obvious links surfaced
   - `anomaly_detection`: Surprise value, statistical rigor
   - `trend_synthesis`: Narrative coherence, causal reasoning
   - `cited_analysis`: Argument structure, evidence-conclusion alignment
   - `analysis`: Depth, actionability, insight beyond the obvious

## Verify claims

Verify **every** factual claim in the answer against the source data. The trace JSON contains the workspace path and the tool call results showing what files were accessed. Read the actual source files and check each number, name, and assertion. Report each claim as VERIFIED, INCORRECT (with the correct value), or UNVERIFIABLE (data not available).

Do not skip any claims. Do not say "plausible" — verify or mark unverifiable.

## Score

Score each dimension 1-5 with a brief justification citing specific parts of the answer.

| Score | Meaning |
|-------|---------|
| 5 | Expert-level — would satisfy the named experts |
| 4 | Strong — correct and insightful, minor gaps |
| 3 | Adequate — covers the basics, lacks depth or nuance |
| 2 | Weak — significant gaps, errors, or superficiality |
| 1 | Failed — wrong, unsupported, or missed the point |

## Output

Present results to the user, then persist them.

### Display

1. **Trace**: workspace, question, model, cost, wall time
2. **Experts**: who would judge this and why
3. **Rubric scores**: table with dimension, score, justification
4. **Claims**: table with claim, verdict, evidence
5. **Overall**: 1-2 sentence summary of what the experts would say

### Persist

Write a JSON file next to the trace with the same name but `.eval.json` extension. For example, if the trace is at `traces/model/workspace/slug.json`, write to `traces/model/workspace/slug.eval.json`.

The eval file structure:

```json
{
  "trace_file": "slug.json",
  "timestamp": "YYYY-MM-DD HH:MM",
  "question": "the question text",
  "category": "the category",
  "workspace": "the workspace",
  "experts": ["Expert Name 1", "Expert Name 2"],
  "scores": {
    "accuracy": {"score": 4, "justification": "..."},
    "citation_quality": {"score": 3, "justification": "..."}
  },
  "claims": [
    {"text": "claim text", "verdict": "VERIFIED", "evidence": "..."}
  ],
  "overall_score": 3.5,
  "overall": "1-2 sentence expert summary"
}
```
