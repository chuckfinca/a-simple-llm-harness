# Research: Separating Environment Description from Task Methodology

Date: 2026-03-16

## The Specific Problem

The harness has a single tool: `run_python` (execute Python in a sandbox).
The system prompt currently contains both:

1. **Environment description** -- what the sandbox is, how stdout works,
   what libraries are installed, that `/workspace` contains files
2. **Search methodology** -- use synonyms, verify passages, search before
   reading, cite sources

The tension: not every question requires document search. A pure computation
question ("What is the integral of x^2?") gets burdened with irrelevant
search/citation instructions. But the harness cannot know in advance which
questions need search and which do not.

With dedicated tools (list_files, search_files, read_file), methodology
guidance naturally lives in tool descriptions. With a single `run_python`
tool, there is no obvious place to put it besides the system prompt.

---

## Pattern 1: Everything in the System Prompt (Current Approach)

**Who does this:** The current harness. OpenAI's Code Interpreter. Codex CLI.

**How it works:** The system prompt contains both environment facts and
methodology guidance. The model is expected to use its own judgment about
which instructions are relevant to a given question.

**Evidence from production:**

OpenAI's Codex CLI system prompt mixes environment description ("You are
Codex, running in the Codex CLI on a user's computer") with methodology
("Think first. Before any tool call, decide ALL files/resources you will
need. Batch everything."). There is no separate channel for methodology.

The current harness `system.md` does the same: environment facts (stdout
captured, truncation limit, packages installed) sit alongside behavioral
guidance (do as much as possible per turn, derive responses from evidence).

**Pros:**
- Simplest architecture. No routing, no classification, no dynamic assembly.
- System prompt has the highest instruction authority for most models.
  Research from SysBench (ICLR 2025) confirms that system messages produce
  more focused, specific responses than equivalent instructions in user
  messages.
- Prompt caching works well because the system prompt is static per session.

**Cons:**
- Every question pays the token cost of all methodology, even when
  irrelevant.
- The model must decide which parts of the prompt apply. Empirical evidence
  (PromptHub experiments, SysBench) shows that instruction following degrades
  as system prompts grow, especially past ~3,000 tokens.
- For mixed task types, irrelevant instructions can confuse the model.
  Anthropic warns that "a focused 300-token context often outperforms an
  unfocused 113,000-token context."

**When to use this:** When the system prompt is short enough that the
overhead does not matter. The current harness `system.md` is ~120 words.
At this size, the cost of always including search methodology is negligible.
The problem only becomes real if methodology guidance grows substantially.

---

## Pattern 2: Methodology in the User Message (Alongside the Question)

**Who does this:** Anthropic's multi-agent research system (per-subagent
task descriptions). Google ADK (dynamic instruction templates). Many RAG
evaluation frameworks (per-question instructions).

**How it works:** The system prompt describes only the environment and
general behavior. Task-specific methodology is prepended or appended to
the user message.

```
System: You execute Python code in a sandbox. /workspace has text files.
        stdout is captured, truncated at 50000 chars. pandas/numpy/scipy
        installed.

User:   [Methodology: This question requires searching workspace files.
        Search before reading. Use varied search terms. Verify passages
        by reading surrounding context. Cite sources with bracketed
        references.]

        What does Federalist No. 10 argue about factions?
```

**Evidence from production:**

Google ADK explicitly supports dynamic instruction injection through
template variables in the agent instruction field: `{var}` syntax inserts
runtime values from session state. This enables per-task customization
without modifying the agent's base instructions.

Anthropic's multi-agent research system gives each subagent "an objective,
an output format, guidance on the tools and sources to use, and clear task
boundaries" -- these are injected per-task, not set globally.

EleutherAI's lm-evaluation-harness takes this further: each benchmark
defines its own `doc_to_text` prompt template in YAML. The system prompt
(if any) stays generic; task-specific framing lives in the per-question
template. This is the closest analog to an eval harness with heterogeneous
question types.

**Pros:**
- Clean separation. The system prompt is stable and cache-friendly. Task
  methodology varies per question without invalidating the prompt cache.
- Models see task methodology immediately before the question -- recency
  bias works in your favor (instructions near the question get more
  attention than instructions at the top of a long system prompt).
- No wasted tokens. Pure computation questions get no search methodology.

**Cons:**
- Requires a classifier or routing logic to decide which methodology to
  inject. This adds complexity and a potential point of failure.
- Instructions in the user message have lower authority than system message
  instructions for most models. The PromptHub experiment showed system
  message placement produces "more targeted guidance" while user message
  placement produces "broader, more general outputs."
- If the model disobeys methodology guidance, it is harder to debug --
  was the classification wrong, or did the model ignore the instructions?

**When to use this:** When you have clearly distinct task types (search vs.
compute vs. comparison) and the methodology for each is substantial enough
that including all of them in the system prompt would degrade performance.
The collect_traces.py script already categorizes questions (single_doc,
multi_doc, enumeration, comparison, single_fact) -- these categories could
drive methodology selection.

---

## Pattern 3: Methodology in a Workspace File (Agent Reads It)

**Who does this:** Claude Code (CLAUDE.md files). Anthropic's long-running
agents (claude-progress.txt, feature requirements files). LangChain's
filesystem context engineering pattern.

**How it works:** Search methodology is stored as a file in the workspace
(e.g., `/workspace/README.md` or `/workspace/.methodology.md`). The system
prompt mentions its existence. The agent reads it when it encounters a
search task.

```
System: You execute Python code in a sandbox. /workspace has text files.
        A file at /workspace/SEARCH_GUIDE.md describes how to search
        effectively. Read it when you need to search the workspace.
```

**Evidence from production:**

LangChain's filesystem context engineering blog explicitly recommends:
"Rather than stuffing all instructions into the system prompt (and bloating
context) you can store them as files and let the agent dynamically read
them as needed."

Anthropic's long-running agent architecture uses artifact-based
communication: structured files (feature lists, progress logs) provide
instructions that future sessions read. The system prompt says what files
exist; the files contain the detailed guidance.

Claude Code's CLAUDE.md pattern is the same principle at a different level:
project-specific instructions in a file that the agent reads at session
start. The key recommendation is "keep CLAUDE.md concise -- break up
information into separate files and reference them."

The Agent READMEs paper (arXiv:2511.12884) studied this pattern empirically
and found that workspace-based instructions are most effective when they
cover project architecture and specific workflows rather than generic
guidance.

**Pros:**
- System prompt stays minimal. Methodology only enters the context when
  the agent reads the file -- which only happens when it is searching.
- The file is version-controlled alongside the workspace data.
- Progressive disclosure: the agent decides when it needs the guidance.
- No classification logic needed. The agent self-selects.

**Cons:**
- Costs an extra tool call (one turn of latency and tokens) to read the
  methodology file. For a harness where each turn is expensive, this is
  a real cost.
- Instructions read via tool calls land in the context as tool results,
  which have lower authority than system prompt instructions. Models
  are more likely to deviate from tool-result guidance than system prompt
  guidance.
- The agent might not read the file. If the model decides it already knows
  how to search, it may skip the methodology entirely. This is the core
  risk of progressive disclosure.
- Open Interpreter's experience with RAG-injected hints was negative:
  "suffers from typical RAG limitations -- injecting irrelevant information
  that doesn't meaningfully improve performance."

**When to use this:** When the methodology guidance is long (hundreds of
tokens) and the harness has many capabilities, making it impractical to
include all guidance in the system prompt. Not recommended when the
guidance is short and universally applicable.

---

## Pattern 4: Dynamic System Prompt Assembly per Question

**Who does this:** No widely-used production system does this for
per-question variation within a session. Several do it per-session
(Claude Code, Open Interpreter, Google ADK).

**How it works:** Before each question, a classifier or router determines
the question type, selects the appropriate methodology module, and
assembles a custom system prompt.

```python
def classify_question(question: str) -> str:
    # Could be rule-based, embedding-based, or LLM-based
    if any(kw in question.lower() for kw in ["search", "find", "document"]):
        return "search"
    return "compute"

def build_messages(question: str, base_prompt: str):
    qtype = classify_question(question)
    system = base_prompt
    if qtype == "search":
        system += "\n\n" + SEARCH_METHODOLOGY
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
```

**Evidence from research:**

The TEMPERA framework (arXiv) uses a reinforcement learning agent to
dynamically edit prompts at test time per query. Academic work on
"Automatic Prompt Selection" (arXiv:2404.02717) clusters training data,
generates candidate prompts per cluster, and trains a prompt evaluator
to select the best prompt for each new input.

Both show measurable improvement over static prompts on heterogeneous
benchmarks. But both add significant infrastructure complexity.

**Pros:**
- Maximum precision: each question gets exactly the methodology it needs.
- No wasted tokens, no irrelevant instructions.
- Can be implemented simply with keyword heuristics, or more
  sophisticatedly with an embedding classifier.

**Cons:**
- Breaks prompt caching if the system prompt changes per question.
  Within a multi-turn session, changing the system prompt mid-session
  invalidates the KV cache from that point. For a batch eval harness
  where each question is a fresh session, this is less of an issue.
- Classification errors route questions to the wrong methodology.
  A question like "What is the population of Japan according to the
  documents?" is both "search" and "single_fact" -- misclassification
  means missing instructions.
- Adds a layer of indirection that makes debugging harder. When the
  agent fails, you need to check both the classification and the
  assembled prompt.

**When to use this:** For batch eval harnesses (like collect_traces.py)
where each question runs in an isolated session. The question category
is already known (it is part of the Question dataclass). This is the
pattern that would be easiest to implement in the existing codebase.

---

## Pattern 5: Thin System Prompt + Model Judgment (Trust the Model)

**Who does this:** Anthropic's recommended starting point. The "start
minimal" philosophy.

**How it works:** The system prompt describes the environment minimally.
No methodology guidance at all. The model uses its own training to decide
how to search, when to cite, etc.

```
System: Execute Python code in a sandbox. /workspace has text files.
        stdout captured, truncated at 50000 chars. pandas/numpy/scipy
        installed. Derive responses from workspace evidence.
```

**Evidence from production:**

Anthropic's context engineering guidance says: "Start by testing a minimal
prompt with the best model available to see how it performs on your task,
and then add clear instructions and examples to improve performance." The
emphasis is on adding methodology only when you observe specific failure
modes.

The "right altitude" principle: "specific enough to guide behavior
effectively, yet flexible enough to provide the model with strong
heuristics." Two failure modes: brittle over-specification and vague
under-specification. Methodology instructions risk the former.

**Pros:**
- Minimal token cost. Maximum prompt cache efficiency.
- No irrelevant instructions for any question type.
- Frontier models (Claude Sonnet/Opus, GPT-5+) are often good at
  deciding search strategy on their own -- the methodology guidance
  may be telling them what they already know.
- Easy to test: run the eval suite with and without methodology to
  measure the delta.

**Cons:**
- Weaker models or models without strong agentic training may fail
  without guidance. The harness needs to work across models via LiteLLM.
- Specific failure modes (not using synonyms, not verifying passages,
  not citing sources) may not emerge until production.
- "Derive responses from evidence" is itself methodology -- the question
  is where to draw the line.

**When to use this:** As the baseline to test against. If the eval suite
passes without methodology, you do not need it. Add methodology only
for specific observed failures.

---

## What the Evidence Actually Says

### System Prompt vs. User Message Placement

The SysBench benchmark (ICLR 2025) found that system message following
is "still a challenging task" and that performance degrades in multi-turn
conversations. However, system messages produce more focused, specific
responses than the same instructions in user messages.

PromptHub's empirical comparison confirmed: system message placement
yields "more targeted guidance" while user message placement yields
"broader, more general outputs" and sometimes triggers AI disclaimer
behavior.

**Implication:** If methodology needs high compliance, put it in the
system prompt. If it is guidance the model can use or ignore, the user
message works.

### Dynamic vs. Static Prompting

No empirical study directly compares static system prompts vs. per-question
dynamic prompts for code-execution sandbox agents. The closest evidence:

- Academic work (TEMPERA, Automatic Prompt Selection) shows dynamic
  prompt selection improves performance on heterogeneous benchmarks by
  optimizing for each input type.
- Manus AI prioritizes cache hit rate as their #1 production metric,
  which argues against per-question system prompt variation.
- The EleutherAI evaluation harness uses per-task prompt templates (via
  YAML config) as its standard approach for heterogeneous benchmarks.

**Implication:** For a batch eval harness where each question is a fresh
API call, dynamic prompting is feasible. For a multi-turn interactive
session, static system prompts with methodology in the user message is
the pragmatic choice.

---

## Recommendation for This Harness

### Current state analysis

The current `system.md` is ~120 words. It contains:
- Environment facts (sandbox, stdout captured, truncation limit, packages)
- One behavioral instruction (do as much as possible per turn)
- One grounding instruction (derive responses from evidence)

Search methodology (synonyms, verification, citation format) is *not*
currently in the system prompt -- it was removed at some point. The
MEMORY.md mentions "Prompts split into goal.md and methodology.md" but
these files no longer exist in the codebase. The system prompt is
already quite lean.

### Decision framework

The key question: **Does adding search methodology to the system prompt
improve eval scores enough to justify the extra tokens?**

This is empirically testable with the existing eval suite. Run
collect_traces.py with and without methodology guidance. If the delta
is small, Pattern 5 (trust the model) wins. If the delta is large,
proceed to choose where the methodology lives.

### Recommended approach: Tiered

**Tier 1 (now -- keep it simple):**
Keep the system prompt lean as it is. If specific failure modes emerge
(agent not searching, not citing, not using synonyms), add targeted
instructions to the system prompt. The current prompt is well under the
~3,000 token degradation threshold.

**Tier 2 (if methodology grows past ~300 words):**
Split the system prompt into two markdown files:
- `environment.md` -- sandbox facts, packages, output limits
- `methodology.md` -- search strategy, citation format, verification

Both load at session start. The environment section is always included.
The methodology section is included when `workspace` is configured
(which is already how `build_system_prompt` works). This is the existing
conditional assembly pattern, just with finer granularity.

```python
def build_system_prompt(*, base_prompt, workspace=None):
    sections = [base_prompt]
    if workspace:
        sections.append(ENVIRONMENT_MD.format(...))
        sections.append(METHODOLOGY_MD)  # search + citation guidance
    return "\n\n".join(sections)
```

**Tier 3 (if supporting radically different task types):**
For batch eval (collect_traces.py), inject category-specific methodology
in the user message. The Question dataclass already has `category`.
The system prompt stays environment-only. Methodology is a dict keyed
by category.

```python
CATEGORY_GUIDANCE = {
    "single_doc": "Search for the specific document, read it, cite it.",
    "multi_doc": "Search broadly, read multiple files, synthesize.",
    "enumeration": "Search with multiple terms, compile a list.",
    "comparison": "Find both subjects, read both, compare.",
    "single_fact": "Search for the fact, verify it, state it.",
}

def build_user_message(question: Question) -> str:
    guidance = CATEGORY_GUIDANCE.get(question.category, "")
    if guidance:
        return f"[Approach: {guidance}]\n\n{question.text}"
    return question.text
```

This adds zero complexity to the interactive CLI path. It only applies
to the batch eval path where categories are already defined.

### What NOT to do

- **Do not build a question classifier for the interactive CLI.** The
  added complexity and failure modes are not justified at this scale.
- **Do not put methodology in workspace files.** The extra tool call
  cost and reduced instruction authority are not worth it when the
  methodology fits comfortably in the system prompt.
- **Do not change the system prompt per question in a multi-turn
  session.** This breaks prompt caching and introduces confusing
  debugging dynamics.
- **Do not add methodology guidance preemptively.** Test first. If the
  model already searches effectively, the guidance is wasted tokens.

---

## Open Questions

1. **What is the actual eval delta?** Run collect_traces.py with the
   current lean prompt, then add search/citation methodology, and
   compare pass rates. This is the only way to know if methodology
   guidance matters for the models being used.

2. **Does category-specific guidance in the user message help?** For
   the batch eval, this is easy to A/B test. Does "Search broadly,
   read multiple files" for multi_doc questions improve over the
   generic prompt?

3. **How much does prompt caching actually save?** The MEMORY.md notes
   that cache verification is pending. If caching is not working, the
   argument for keeping the system prompt stable loses weight.

4. **Where did the old methodology files go?** MEMORY.md references
   "goal.md" and "methodology.md" as the prompt split, but these no
   longer exist. Was the methodology intentionally removed? If so, was
   performance unaffected? That would be strong evidence for Pattern 5.

---

## Sources

### Empirical Studies
- [SysBench: Can LLMs Follow System Messages? (ICLR 2025)](https://arxiv.org/html/2408.10943v1)
- [PromptHub: System Messages Experiments](https://www.prompthub.us/blog/everything-system-messages-how-to-use-them-real-world-experiments-prompt-injection-protectors)
- [Automatic Prompt Selection for LLMs (arXiv)](https://arxiv.org/html/2404.02717v1)
- [Agent READMEs: Empirical Study (arXiv)](https://arxiv.org/pdf/2511.12884)

### Production System Architectures
- [Anthropic: Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Anthropic: Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Anthropic: Building Effective Agents](https://www.anthropic.com/research/building-effective-agents)
- [OpenAI: Code Interpreter](https://developers.openai.com/api/docs/guides/tools-code-interpreter/)
- [OpenAI: Codex Prompting Guide](https://developers.openai.com/cookbook/examples/gpt-5/codex_prompting_guide/)
- [Google ADK: LLM Agents](https://google.github.io/adk-docs/agents/llm-agents/)
- [LangChain: Filesystems for Context Engineering](https://blog.langchain.com/how-agents-can-use-filesystems-for-context-engineering/)

### Open Interpreter
- [How It's Built: Open Interpreter](https://sean.lyn.ch/how-its-built-open-interpreter/)

### Eval Harness Architectures
- [EleutherAI lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness)

### Prompt Placement Patterns
- [VS Code: Prompt Files vs Custom Instructions vs Custom Agents](https://gist.github.com/burkeholland/435ab18c549ddbefde1846165e8b2e08)
- [Anthropic: CLAUDE.md Best Practices](https://claude.com/blog/using-claude-md-files)
- [Arize: CLAUDE.md Best Practices](https://arize.com/blog/claude-md-best-practices-learned-from-optimizing-claude-code-with-prompt-learning/)

### Cache Considerations
- [Manus: Context Engineering Lessons](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [Don't Break the Cache (arXiv, Jan 2026)](https://arxiv.org/html/2601.06007v2)
