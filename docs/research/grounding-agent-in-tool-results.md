# Grounding LLM Agents in Tool Results

Research into preventing two specific failure modes:
1. Model answers without calling any tools (skips search entirely)
2. Model does shallow search (filename matching only) instead of deep content search

## The Two Failures in Context

Looking at the harness code, the agent loop in `agent.py` uses `tool_choice` at its
default (`auto`), meaning the model decides freely whether to call tools. The system
prompt in `prompts/workspace.md` says "Use list_files, search_files, and read_file to
explore them" but does not explicitly prohibit answering from training data. The
`search_strategy.md` prompt guides *how* to search but does not mandate *that* the
model must search. These are the root causes.

---

## 1. API-Level Enforcement: `tool_choice` Parameter

The most direct mechanism available today. Both Anthropic and OpenAI provide
API-level parameters that force tool use before the model can generate text.

### Anthropic Claude

Four options for `tool_choice`:
- `auto` (default) -- model decides whether to call tools
- `any` -- model MUST call one of the provided tools (cannot return text only)
- `tool` -- model MUST call a specific named tool
- `none` -- model cannot use tools

When `tool_choice` is `any` or `tool`, the API prefills the assistant message to
force a tool call. The model will not emit natural language before `tool_use`
content blocks, even if explicitly asked to.

**Limitation with extended thinking**: `tool_choice: any` and `tool_choice: tool`
are NOT compatible with extended thinking. Only `auto` and `none` work with
thinking enabled. This is a significant constraint for agents that need both
forced tool use and chain-of-thought reasoning.

### OpenAI

Three options:
- `auto` (default)
- `required` -- model MUST call one or more functions
- `{"type": "function", "function": {"name": "..."}}` -- forces a specific function

### Application to the Harness

The harness could use `tool_choice: any` on the first turn of each user question
to guarantee at least one tool call, then switch to `tool_choice: auto` for
subsequent turns in the agent loop. This is the "forced first retrieval" pattern.

**Tradeoff**: This forces a tool call even when unnecessary (e.g., "what time is
it?" would still force a file search). The harness would need logic to determine
when forced tool use is appropriate -- essentially, when workspace files are
relevant to the question.

Sources:
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use
- https://platform.claude.com/cookbook/tool-use-tool-choice
- https://community.openai.com/t/new-api-feature-forcing-function-calling-via-tool-choice-required/731488

---

## 2. System Prompt Patterns That Enforce Tool Use

When API-level enforcement is too coarse (or incompatible with extended thinking),
prompt engineering is the primary lever. Research converges on several patterns:

### Pattern A: Explicit Prohibition + Mandatory Retrieval

The strongest prompt pattern is a direct prohibition against answering from
training data, combined with a mandatory retrieval step.

Example structure:
```
You are a research assistant with access to a document workspace.

CRITICAL RULES:
- You MUST search the workspace before answering any question about its contents.
- NEVER answer questions about the documents from memory or training data.
- If you think you know the answer, search anyway to verify and to find the
  exact source text for citations.
- If search returns no results, say so. Do not fill in from background knowledge.

Answer ONLY using information found through your tools in this conversation.
```

This pattern is widely documented in RAG system design. The key insight from
practitioners: "Without clear instructions, the model will ignore your beautifully
retrieved context and hallucinate an answer. Your prompt is the final safeguard."

### Pattern B: Role-Based Framing

Frame the agent's identity around tool use:
```
You are a document analyst. You do not have knowledge of these documents --
you can only learn about them by using your search and read tools. Treat every
question as if you are encountering these documents for the first time.
```

This works because it reframes the task. Instead of "answer this question" (which
the model can attempt from training data), it becomes "investigate these documents"
(which requires tool use by definition).

### Pattern C: Procedure Specification

Specify the exact procedure the agent must follow:
```
For every question about the workspace documents:
1. First, identify 3-5 search terms from the question
2. Run search_files for each term
3. Read the most relevant files found
4. Only after reading the source material, synthesize your answer
5. Cite specific passages with line numbers

Never skip steps 1-3, even if you believe you know the answer.
```

This is essentially encoding the ReAct pattern into the system prompt. It works
better than vague instructions because it gives the model a concrete plan to
follow rather than a prohibition to obey.

### Pattern D: Negative Examples

Show the model what NOT to do:
```
BAD (answering without tools):
  User: "What does Federalist No. 10 argue?"
  Assistant: "Federalist No. 10 argues that factions are..."
  [This is wrong because you did not search or read any files]

GOOD (searching first):
  User: "What does Federalist No. 10 argue?"
  Assistant: [calls search_files with "factions"]
  Assistant: [calls read_file on the matching document]
  Assistant: "According to the document (lines 42-58), Federalist No. 10 argues..."
```

Few-shot examples are among the most effective prompt engineering techniques.
Anthropic's context engineering guide states: "For an LLM, examples are the
pictures worth a thousand words."

### What the Research Says About Effectiveness

System prompts are "just tokens the model reads on every forward pass" -- they
condition next-token probabilities but do not provide hard guarantees. A model
can still violate system prompt instructions, especially:
- When the instruction conflicts with strong training signal
- On longer conversations where early instructions get diluted
- When the model is highly confident in its training data answer

This means prompt engineering alone is never 100% reliable. It must be combined
with structural enforcement or evaluation-based detection.

Sources:
- https://www.stackai.com/blog/prompt-engineering-for-rag-pipelines-the-complete-guide-to-prompt-engineering-for-retrieval-augmented-generation
- https://machinelearningmastery.com/prompt-engineering-patterns-successful-rag-implementations/
- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- https://applied-llms.org/

---

## 3. Structural / Architectural Approaches

Beyond prompting and API parameters, there are architectural patterns that make
tool-skipping structurally impossible or detectable.

### Approach A: Two-Phase Architecture (Plan-Then-Execute)

Separate the agent into two phases:
1. **Planning phase**: Model outputs a search plan (which tools to call, with
   what arguments) but does NOT generate an answer
2. **Execution phase**: Harness executes the plan, collects results, then asks
   the model to synthesize an answer from the collected evidence only

This is the ReWOO pattern (Reasoning WithOut Observation). The model produces a
"script" of tool calls with placeholders for results. The harness executes them
all, then makes one final LLM call with all results to generate the answer.

**Advantage**: The model literally cannot answer without tool results because the
answer-generation call only happens after tools have been executed.

**Disadvantage**: Loses the adaptive quality of a ReAct loop -- the model cannot
adjust its search strategy based on intermediate results. Also requires two
distinct prompt templates and more complex orchestration.

### Approach B: Forced First Turn + Adaptive Continuation

A hybrid that addresses the "skips search entirely" failure:
1. First LLM call uses `tool_choice: any` -- forces at least one tool call
2. Subsequent calls use `tool_choice: auto` -- model can call more tools or
   give a final answer

This guarantees the model enters the search space before it can respond. The
adaptive loop then lets it deepen its search based on initial results.

### Approach C: Letta/MemGPT Tool Rules

Letta (formerly MemGPT) introduced a formal tool rules system with four rule
types:
- `InitToolRule(tool_name)` -- this tool MUST be called first when the agent runs
- `TerminalToolRule(tool_name)` -- calling this tool ends agent execution
- `ChildToolRule(tool_name, children)` -- after calling this tool, one of the
  children must be called next
- `ParentToolRule(tool_name, children)` -- this tool must be called before any
  of the children can be called

For a retrieval agent, you would set `InitToolRule("search_files")` to guarantee
search happens before any response. Combined with `TerminalToolRule("send_message")`,
this creates a graph of: search -> (optional intermediate tools) -> respond.

This is the most formally rigorous approach found in the research. It transforms
the agent loop from a free-form "model decides everything" into a constrained
state machine where certain tool sequences are mandatory.

### Approach D: AgentSpec Runtime Enforcement

AgentSpec (ICSE 2026) provides a domain-specific language for specifying runtime
constraints on LLM agents. It uses triggers, predicates, and enforcement actions:
- **Triggers**: `before_action`, `state_change`, `agent_finish`
- **Predicates**: Conditions that must be true
- **Enforcement**: `user_inspection`, `llm_self_examine`, `invoke_action`, `stop`

For the grounding problem, a rule could specify: "before `agent_finish`, verify
that at least one `search_files` or `read_file` tool was called in this turn."
If the predicate fails, enforcement could invoke a corrective action (force a
search) or stop execution.

Evaluation shows AgentSpec prevents unsafe executions in 90%+ of cases with
millisecond-level overhead.

### Approach E: Post-Hoc Validation in the Agent Loop

Instead of preventing tool-free responses, detect and remediate them:

```python
# Pseudocode for the agent loop
for turn in range(max_turns):
    response = llm.call(messages, tools, tool_choice="auto")

    if response.is_text_only and turn == 0 and workspace_question:
        # Model tried to answer without searching -- reject and retry
        messages.append({
            "role": "user",
            "content": "You must search the workspace documents before answering. "
                       "Please use search_files to find relevant passages first."
        })
        continue

    # ... normal tool execution ...
```

This is a guardrail approach: let the model try, but catch the failure and
redirect. It has the advantage of being simple to implement and not requiring
API-level changes. The disadvantage is wasted tokens on the rejected response.

Sources:
- https://arxiv.org/abs/2503.18666 (AgentSpec)
- https://docs.letta.com/guides/agents/tool-rules (Letta tool rules)
- https://www.wollenlabs.com/blog-posts/navigating-modern-llm-agent-architectures-multi-agents-plan-and-execute-rewoo-tree-of-thoughts-and-react

---

## 4. Addressing Shallow Search (Failure Mode 2)

The second failure -- model does filename matching instead of content search --
is subtler. The model calls `list_files` to find files with relevant names, then
reads them directly, bypassing `search_files` entirely. This misses relevant
content in files whose names do not match the query.

### Why This Happens

The model takes the path of least resistance. `list_files` with a pattern is a
single tool call that returns "probably relevant" files. `search_files` requires
the model to generate search terms, potentially make multiple calls, and process
more results. The model optimizes for fewer tool calls unless instructed otherwise.

### Mitigation Strategies

**Strategy 1: Explicit instructions in tool descriptions**

The current `list_files` description says "Use this to discover available files
before reading or searching." This subtly suggests list_files is a precursor to
search, but the model can short-circuit by going list -> read -> answer.

A better description would make the limitation explicit:
```
"List files in the workspace directory. Returns file paths and sizes.
WARNING: File names may not reflect file contents. Do not use filename
matching as a substitute for content search. Always use search_files to
find relevant content across all documents."
```

**Strategy 2: Prompt instructions that mandate content search**

Add to the system prompt:
```
IMPORTANT: File names in this workspace do not reliably indicate content.
A document about the judiciary might not have "judiciary" in its filename.
Always use search_files to search document contents, not just list_files
to match filenames. Filename matching alone will miss relevant documents.
```

**Strategy 3: Remove or constrain the `list_files` pattern parameter**

If `list_files` did not support regex filtering on filenames, the model could
not use it as a content-discovery shortcut. It would only be useful for getting
an overview of the workspace, and the model would be forced to use `search_files`
for content-based discovery.

**Strategy 4: Tool design following Anthropic's guidance**

Anthropic's "Writing Tools for Agents" blog recommends that truncated or limited
responses can "prompt-engineer agents to pursue more token-efficient strategies,
like making many small and targeted searches." If `list_files` returns only
filenames (no content preview), the model has no information to judge relevance
and must search content. If `search_files` returns rich context (surrounding
lines), it becomes the obviously better tool for finding relevant content.

**Strategy 5: Few-shot examples showing multi-search patterns**

Include examples in the system prompt showing the expected search workflow:
```
Example: "Which papers discuss the judiciary?"

Step 1: search_files("judiciary")     -> found in papers 78, 79
Step 2: search_files("judicial")      -> found in papers 78, 79, 80, 81
Step 3: search_files("court|courts")  -> found in papers 78, 79, 80, 81, 82, 83
Step 4: search_files("judge|judges")  -> found in papers 78, 79, 80, 81
Step 5: read_file on each unique paper found
Step 6: synthesize answer from all read content
```

Sources:
- https://www.anthropic.com/engineering/writing-tools-for-agents
- https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents

---

## 5. Citation Requirements as a Grounding Mechanism

Requiring citations creates an indirect enforcement mechanism: the model cannot
cite a source it has not read, so citation requirements implicitly force tool use.

### How This Works

If the system prompt requires inline citations with line numbers from tool
results, the model faces a choice:
- Answer from training data with no citations (violates the citation rule)
- Answer from training data with fabricated citations (detectable -- line numbers
  will not match actual file content)
- Actually search and read files, then cite real passages (compliant)

### Limitations

Research shows that citation hallucinations persist even as factual accuracy
improves. Models can fabricate plausible-looking citations. One study found
models achieve 62-88% self-citation compliance rates depending on the model,
with 2-19% citation hallucination rates.

### Mechanical Verification

A recent paper (arXiv 2512.12117) extends RAG with mechanical citation
verification: requiring LLMs to cite specific line ranges that must overlap
retrieved chunks, enforced through interval arithmetic rather than trusting
model outputs. This prevented hallucination in 100% of cases where LLMs
attempted to cite non-existent files or invalid line ranges.

**Application to the harness**: After the agent produces its final answer,
a post-processing step could verify that every cited file and line range
was actually returned by a tool call in the conversation history. If citations
reference files or lines not present in tool results, reject the response.

Sources:
- https://arxiv.org/html/2512.12117v1
- https://medium.com/@prestonblckbrn/exploring-llm-citation-generation-in-2025-4ac7c8980794

---

## 6. Evaluation-Based Detection

Rather than preventing the failure, detect it and iterate.

### Tool Compliance Metrics

Track in evaluations:
- **Tool call rate**: percentage of responses that included at least one tool call
- **Search depth**: number of distinct search_files calls per response
- **Coverage**: number of unique files read per response
- **Citation validity**: percentage of citations that reference actual tool results

### Assertion-Based Testing

The "Applied LLMs" guide recommends assertion-based unit tests that verify:
- Model references specific sources when available
- Outputs acknowledge resource limitations when applicable
- Generated responses derive from provided context rather than hallucination

For the harness, test cases could assert:
- "What does Federalist No. 10 argue about factions?" MUST trigger search_files
- Response MUST contain citations to specific lines
- Response MUST NOT contain claims not supported by cited passages

### The "Intern Test"

From applied-llms.org: evaluate whether a human intern could succeed with the
same inputs. If the system prompt says "answer from these documents" but the model
answers from training data, that is equivalent to an intern ignoring the documents
and Googling the answer -- a clear process violation that should fail evaluation.

Sources:
- https://applied-llms.org/
- https://deepchecks.com/llm-agent-evaluation/

---

## 7. Recommended Approach for the Harness

Based on this research, a layered strategy combining multiple techniques:

### Layer 1: System Prompt (Cheapest, Immediate)

Strengthen the system prompt with:
- Explicit prohibition: "NEVER answer from training data about workspace content"
- Role framing: "You have no prior knowledge of these documents"
- Procedure specification: numbered steps requiring search before synthesis
- Few-shot example showing the expected search-then-cite workflow

### Layer 2: Structural Enforcement (Most Reliable)

Implement forced-first-retrieval in the agent loop:
- Use `tool_choice: any` on the first LLM call for workspace questions
- Switch to `tool_choice: auto` on subsequent turns
- Or: detect text-only first responses and inject a redirect message

### Layer 3: Tool Design (Subtle but Effective)

- Weaken `list_files` as a content-discovery tool (remove or de-emphasize the
  pattern parameter, clarify that filenames do not indicate content)
- Strengthen `search_files` descriptions to emphasize it as the primary
  content-discovery mechanism
- Ensure tool return values make search results more informative than file listings

### Layer 4: Citation Verification (Post-Hoc Safety Net)

- Require citations in the system prompt (already done)
- Add mechanical verification: check that cited files and line numbers appear
  in tool results from the conversation
- Reject responses with unverifiable citations

### Layer 5: Evaluation (Ongoing Measurement)

- Track tool call rate, search depth, citation validity across test cases
- Flag responses that skip search or cite non-existent sources
- Use this data to iterate on prompts and structural enforcement

---

## Summary of Techniques by Reliability

| Technique                          | Reliability | Complexity | Notes                              |
|------------------------------------|-------------|------------|------------------------------------|
| `tool_choice: any` (API)           | Very high   | Low        | Incompatible with extended thinking |
| Letta-style tool rules             | Very high   | Medium     | Requires custom agent loop logic    |
| Two-phase plan-then-execute        | Very high   | High       | Loses adaptive search capability    |
| Post-hoc detection + retry         | High        | Low        | Wastes tokens on rejected response  |
| Citation verification              | High        | Medium     | Catches fabricated citations        |
| System prompt prohibition          | Medium      | Low        | Model can still violate             |
| Few-shot examples                  | Medium      | Low        | Most effective prompt technique     |
| Tool description engineering       | Medium      | Low        | Nudges but does not guarantee       |
| Role-based framing                 | Medium      | Low        | Changes the model's self-concept    |
| Evaluation / testing               | N/A         | Medium     | Detection, not prevention           |
