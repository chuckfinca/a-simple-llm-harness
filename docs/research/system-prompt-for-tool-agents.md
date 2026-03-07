# Research: System Prompts for Tool-Use Agents

Date: 2026-03-06

## The Problem

The harness has six tools (run_python, calculator, get_current_time, list_files,
search_files, read_file) and a configurable workspace directory, but the current
system prompt is:

```
You are a helpful assistant. Use the provided tools when appropriate.
```

This tells the model nothing about the workspace, nothing about which tools
exist, and nothing about how to use them effectively. The model ignores the file
exploration tools because it has no reason to believe they exist or that there is
a workspace to explore.

---

## 1. How Leading Tools Construct System Prompts

### Claude Code: Modular Prompt with Environment Context

Claude Code uses a modular system prompt architecture of 110+ individual prompt
strings that are conditionally assembled at runtime. The base prompt is small
(~269 tokens: "You are Claude Code, Anthropic's official CLI for Claude"), but
it dynamically includes:

- **Environment context**: working directory, OS, git status, shell type
- **Tool descriptions**: Each of the 18 builtin tools has a dedicated markdown
  description file that is loaded into the system prompt text -- separate from
  and in addition to the tool schemas
- **Tool usage guidance**: Explicit behavioral rules like "Use Read instead of
  cat", "Use Glob/Grep directly for simple searches", "Prefer Write tool
  instead of shell redirection"
- **Project context**: CLAUDE.md files are loaded into context at session start
- **Conditional sections**: Features, permissions, and sub-agent descriptions
  are included only when relevant

Key insight: Claude Code does NOT rely solely on tool schemas. It includes
**prose descriptions and usage guidance in the system prompt text** that tell
the model when and how to use each tool. The schemas provide the API; the
prompt provides the judgment about when to use which tool.

Sources:
- [Claude Code System Prompts (Piebald-AI)](https://github.com/Piebald-AI/claude-code-system-prompts)
- [Claude Agent Skills Deep Dive](https://leehanchung.github.io/blogs/2025/10/26/claude-skills-deep-dive/)
- [System Prompt Architecture (DeepWiki)](https://deepwiki.com/shanraisshan/claude-code-best-practice/8.4-system-prompt-architecture)

### Smolagents: Auto-Generated Tool Descriptions in Prompt

Smolagents (HuggingFace) takes a template-based approach. When an agent is
initialized, it:

1. Extracts tool metadata (name, description, input types, output type)
2. Formats this into a tool description block
3. Injects it into the system prompt via a `{{tool_descriptions}}` placeholder

The system prompt template has five sections:
1. Introduction -- explains what the agent is and how tools work
2. Tool descriptions -- the `{{tool_descriptions}}` block
3. Expected output format -- Thought/Code/Observation cycles
4. Rules and constraints -- 10 specific behavioral rules
5. Authorization info -- what imports/actions are allowed

Custom prompts MUST include the `{{tool_descriptions}}` placeholder or the
agent will not know about its tools. This confirms: tool schemas alone are not
sufficient; the model needs the tools described in the prompt text.

Sources:
- [Smolagents Guided Tour](https://huggingface.co/docs/smolagents/v0.1.3/en/guided_tour)
- [Building Good Smolagents](https://smolagents.org/docs/building-good-smolagents/)

### Open Interpreter: Role + Environment + Procedures

Open Interpreter's system prompt has three sections:

1. **Role**: "You are a world-class programmer that can complete any goal by
   executing code."
2. **[User Info]**: Runtime-injected environment details -- username, current
   working directory, OS. This tells the model where it is.
3. **[Recommended Procedures]**: Dynamically loaded guidance from a RAG service
   about how to accomplish common tasks.

The prompt structure adapts based on the model being used and whether OS mode
is enabled. When OS mode is on, detailed API documentation for computer
interaction is included.

Source:
- [How It's Built: Open Interpreter](https://sean.lyn.ch/how-its-built-open-interpreter/)

### Aider: Repo Map as Prompt Context

Aider does not use tools in the traditional sense. Instead, it injects a
**repo map** directly into the prompt -- a compressed table of contents of the
codebase showing file paths and key symbols. This gives the model awareness
of the workspace without tool calls.

The repo map is generated at runtime using tree-sitter, PageRank, and a token
budget. It defaults to ~1,024 tokens and expands when the model needs broader
awareness.

Source:
- [Aider Repository Map](https://aider.chat/docs/repomap.html)

---

## 2. Tool Schemas vs. System Prompt Descriptions

### The Short Answer: You Need Both

Tool schemas (the JSON structure in the `tools` parameter) provide the API
contract -- what arguments a tool takes and their types. But schemas alone do
not tell the model:

- **When** to use a tool vs. answering from memory
- **Why** to prefer one tool over another
- **In what order** to chain tools
- **What environment** the tools operate against

Every production tool-use system examined reinforces tool awareness in the
system prompt, not just the schema.

### When Schemas Alone Are Sufficient

For strong models (GPT-4o, Claude Sonnet/Opus, Gemini Pro) with **well-named
tools and good descriptions in the schema**, the model will figure out basic
tool usage on its own. Schemas are sufficient when:

- There are only 1-3 simple tools with obvious names
- The user's question directly implies a tool (e.g., "what time is it?" with
  a `get_current_time` tool)
- The tools are self-explanatory and do not need sequencing

### When the System Prompt Must Reinforce

The system prompt must describe tools when:

- **The model has no reason to know something exists**. If there is a workspace
  directory full of files, the model cannot discover this from tool schemas
  alone. The schema for `list_files` says "List all files in the workspace
  directory" but the model does not know there IS a workspace or what is in it.
- **Tool sequencing matters**. If the correct pattern is "list first, search
  second, read third," this must be stated in the prompt. Schemas have no
  mechanism for expressing workflow.
- **Multiple tools overlap**. When `search_files` and `read_file` could both
  answer a question, the prompt should guide which to prefer.
- **Smaller or quantized models are used**. AnythingLLM documents that smaller
  and quantized models frequently fail to use tools at all -- they need
  explicit prompt-level instruction to trigger tool calls.

### What Anthropic Says

Anthropic's prompting best practices (updated for Claude 4.6) state: "Use the
system prompt to describe when (and when not) to use each function." They
recommend that tool descriptions be "self-contained, robust to error, and
extremely clear with respect to their intended use."

Their context engineering guide adds: "If a human engineer can't definitively
say which tool should be used in a given situation, an AI agent can't be
expected to do better." The implication: make it obvious in the prompt.

Sources:
- [Anthropic Prompting Best Practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- [Anthropic Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [AnythingLLM: Why Agent Not Using Tools](https://docs.anythingllm.com/agent-not-using-tools)
- [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)

---

## 3. Environment Context in System Prompts

### The Consensus: Inject Runtime Environment Info

Every leading tool examined injects environment context at runtime:

| Tool | What It Injects |
|------|----------------|
| Claude Code | Working directory, OS, shell, git status, git branch, recent commits |
| Open Interpreter | Username, current working directory, OS |
| Aider | Repo map (file listing + symbols), git status |
| Smolagents | Tool descriptions (dynamically generated from registered tools) |
| AnythingLLM | System prompt variables (`{current_date}`, custom vars) |

### Should You Include a File Listing?

It depends on corpus size:

- **< 20 files**: Include the file listing directly in the system prompt. The
  token cost is negligible (~5-20 tokens per file) and it immediately tells the
  model what is available without requiring a tool call.
- **20-100 files**: Mention that the workspace exists and what it contains
  ("a collection of 47 historical documents"), but tell the model to use
  `list_files` to see the full inventory. Including 100 filenames in the
  prompt wastes tokens on every API call.
- **100+ files**: Never include a listing. Just describe the workspace and
  point the model at the exploration tools.

### What to Always Include

At minimum, the system prompt should state:

1. **That a workspace exists**: "You have access to a workspace directory
   containing [description of contents]."
2. **What kind of content is in it**: "The workspace contains markdown documents
   about [topic]" or "The workspace contains source code for [project]."
3. **That tools can explore it**: "Use the file exploration tools (list_files,
   search_files, read_file) to find and read relevant content."

Without this, the model has no mental model of its environment. It is like
dropping a new employee at a desk without telling them they have a filing
cabinet.

Sources:
- [Anthropic Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Claude Code System Prompts](https://github.com/Piebald-AI/claude-code-system-prompts)
- [LangChain Context Engineering](https://docs.langchain.com/oss/python/langchain/context-engineering)

---

## 4. Tool Usage Guidance

### Where Does Guidance Go?

Tool usage guidance should appear in **both** the system prompt and the tool
descriptions, serving different purposes:

**In tool descriptions (the schema)**: Explain what the tool does and its
most important usage hint. This is the "local" guidance that the model sees
when it is deciding which tool to call. Examples from the harness:

- list_files: "Use this first to understand what files are available before
  reading or searching."
- search_files: "Use this to find relevant files before reading them."
- read_file: "Prefer search_files first to find relevant files."

These are good -- the harness already has them. But they are not enough
because the model may not even consider these tools if the system prompt
does not establish the context for using them.

**In the system prompt**: Establish the workflow pattern and when to use tools
at all. This is "global" guidance that sets the model's overall strategy.
Examples:

- "When answering questions about the documents in the workspace, start by
  listing files, then search for relevant terms, then read only the files
  that match."
- "Do not read every file sequentially. Search first, read selectively."
- "If search returns no results, try alternative search terms before reading
  files directly."

### The Search-Before-Read Pattern

This is the single most important piece of guidance for file exploration agents.
Without it, models (especially smaller ones) will default to reading every file
one by one -- which is slow, expensive, and fills the context window with
irrelevant content.

Claude Code enforces a cost hierarchy: Glob (cheapest) -> Grep (medium) ->
Read (most expensive). The system prompt explicitly tells the model to prefer
cheaper operations first.

For a simple harness with three file tools, the equivalent hierarchy is:
list_files (cheapest) -> search_files (medium) -> read_file (most expensive).

### Concrete Guidance Pattern

From analysis of all tools examined, the effective pattern is:

```
## Working with workspace files

You have access to a workspace containing [description]. Use these tools to
explore it:

1. list_files -- see what files are available (use this first)
2. search_files -- find relevant content by searching for key terms
3. read_file -- read a specific file's contents

Always search before reading. Do not read files one by one. If a search
returns no results, try different search terms before falling back to
reading files directly.
```

Sources:
- [Anthropic Prompting Best Practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)

---

## 5. Dynamic vs. Static System Prompts

### The Spectrum

| Approach | Description | Example |
|----------|-------------|---------|
| Fully static | Same prompt every time | "You are a helpful assistant." |
| Static with template variables | Same structure, runtime values injected | "Workspace: {path} ({file_count} files)" |
| Conditionally assembled | Sections included/excluded based on config | Include workspace section only if LH_WORKSPACE is set |
| Fully dynamic | Prompt generated per-request based on state | Different prompt based on conversation length, user, etc. |

### What Leading Tools Do

- **Claude Code**: Conditionally assembled. 110+ prompt fragments selected based
  on environment, features, and configuration.
- **Smolagents**: Static template with dynamic tool descriptions injected via
  `{{tool_descriptions}}`.
- **Open Interpreter**: Static template with runtime environment variables
  appended (OS, working directory, username).
- **LangChain**: Advocates middleware-based dynamic prompts that adapt to
  conversation state, user role, and deployment environment.

### What This Harness Should Do

**Static with template variables** is the right level of complexity. The harness
already reads LH_SYSTEM_PROMPT from the environment, so the simplest path is:

1. Read the base system prompt from LH_SYSTEM_PROMPT
2. If LH_WORKSPACE is configured, append a workspace context section with the
   actual path and a brief description

This avoids the complexity of conditional assembly while solving the core
problem: the model does not know the workspace exists.

### Tradeoffs

| Approach | Pro | Con |
|----------|-----|-----|
| Inject file listing into prompt | Model knows files immediately, no tool call needed | Costs tokens on every API call; stale if files change mid-session |
| Just mention workspace exists | Low token cost, always fresh via tool calls | Requires an extra tool call per question to discover files |
| Inject listing + mention tools | Best of both worlds for small corpora | More complex prompt construction |

**Recommendation**: For < 50 files, inject the file listing at startup. For
larger workspaces, just mention the workspace exists and let the model use
list_files.

Sources:
- [LangChain Context Engineering](https://docs.langchain.com/oss/python/langchain/context-engineering)
- [Mastra Dynamic Agents](https://mastra.ai/blog/dynamic-agents)
- [AnythingLLM System Prompt Variables](https://docs.anythingllm.com/features/system-prompt-variables)

---

## 6. Practical Recommendation

### The Problem Restated

The current system prompt:

```
You are a helpful assistant. Use the provided tools when appropriate.
```

This fails because:
- It does not mention the workspace
- It does not name the available tools
- It does not guide tool usage patterns
- It treats file tools the same as calculator/time tools

### Recommended System Prompt Structure

For a harness with 6 tools and a configurable workspace, the system prompt
should have three sections:

**Section 1: Role and capabilities** (static)

Establishes what the agent is and what it can do.

**Section 2: Workspace context** (dynamic, appended at runtime if workspace
configured)

Names the workspace, describes its contents, and establishes the tool
workflow.

**Section 3: Tool guidance** (static)

Brief reminders about tool behavior that do not belong in individual tool
descriptions.

### Concrete Example

```
You are a helpful research assistant with access to tools for computation,
code execution, and file exploration.

## Workspace

You have access to a workspace directory containing documents that may be
relevant to the user's questions. To explore the workspace:

1. Use list_files to see what documents are available.
2. Use search_files to find relevant content by keyword.
3. Use read_file to read specific documents identified by search.

Search before reading. Do not read files sequentially -- search for relevant
terms first, then read only the files that match.

## Tools

- run_python: Execute Python code in a sandboxed environment. numpy, pandas,
  and scipy are available.
- calculator: Evaluate math expressions.
- get_current_time: Get the current UTC time.
- list_files, search_files, read_file: Explore and read workspace documents.

When answering questions about the workspace documents, always use the file
tools to find evidence before answering. Do not guess at document contents.
```

### What Makes This Effective

1. **Names the workspace** -- the model now knows files exist to explore.
2. **Prescribes a workflow** -- search before read, not sequential reading.
3. **Lists all tools with brief descriptions** -- reinforces tool awareness
   beyond what the schemas provide.
4. **Separates tool categories** -- computation tools vs. file tools, so the
   model understands when each group applies.
5. **Sets an evidence standard** -- "use the file tools to find evidence
   before answering" prevents the model from guessing.

### Dynamic Enhancement (Optional)

If the workspace is small (< 50 files), the runtime prompt construction can
append a file listing:

```
## Workspace Contents

The workspace at /path/to/workspace contains 15 documents:
- document-01.md (2.1 KB)
- document-02.md (1.8 KB)
- ...
```

This eliminates the need for a list_files call on every question and gives
the model immediate awareness of what is available.

### What NOT to Do

- **Do not enumerate every tool parameter in the prompt**. The schemas handle
  this. The prompt should describe when/why to use tools, not how to call them.
- **Do not dump file contents into the prompt**. Even for small corpora, this
  wastes tokens. Let the model read files on demand.
- **Do not over-prompt**. Anthropic specifically warns that Claude 4.6 models
  will overtrigger on aggressive tool-use instructions. Use normal language,
  not "CRITICAL: YOU MUST USE list_files FIRST".
- **Do not omit the workspace entirely**. This is the current failure mode.
  The model cannot use tools it does not know it has a reason to use.

---

## Summary: The Five Rules

1. **The system prompt must establish what the environment is.** If there is a
   workspace, say so. If there are files to explore, say what kind.

2. **Tool schemas describe HOW to call tools. The system prompt describes WHEN
   and WHY.** Both are needed. Neither is sufficient alone.

3. **Prescribe the workflow, not just the tools.** "Search before reading" is
   more valuable than listing tool names.

4. **Inject runtime context.** At minimum: workspace path and what it contains.
   For small corpora: the file listing too.

5. **Keep it concise.** Every token in the system prompt is re-sent on every
   API call. A 200-token system prompt that works is better than a 2000-token
   prompt with the same information buried in verbosity.

---

## Sources

### Leading Tool Architectures
- [Claude Code System Prompts (Piebald-AI)](https://github.com/Piebald-AI/claude-code-system-prompts)
- [Claude Agent Skills Deep Dive](https://leehanchung.github.io/blogs/2025/10/26/claude-skills-deep-dive/)
- [System Prompt Architecture (DeepWiki)](https://deepwiki.com/shanraisshan/claude-code-best-practice/8.4-system-prompt-architecture)
- [Smolagents Guided Tour](https://huggingface.co/docs/smolagents/v0.1.3/en/guided_tour)
- [Building Good Smolagents](https://smolagents.org/docs/building-good-smolagents/)
- [How It's Built: Open Interpreter](https://sean.lyn.ch/how-its-built-open-interpreter/)
- [Aider Repository Map](https://aider.chat/docs/repomap.html)

### Prompting Best Practices
- [Anthropic Prompting Best Practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- [Anthropic Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)
- [Giving Claude a Role with System Prompts](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/system-prompts)

### Tool Use and Agent Design
- [AnythingLLM: Why Agent Not Using Tools](https://docs.anythingllm.com/agent-not-using-tools)
- [LangChain Context Engineering](https://docs.langchain.com/oss/python/langchain/context-engineering)
- [The Rise of Context Engineering (LangChain Blog)](https://blog.langchain.com/the-rise-of-context-engineering/)
- [Mastra Dynamic Agents](https://mastra.ai/blog/dynamic-agents)
- [AnythingLLM System Prompt Variables](https://docs.anythingllm.com/features/system-prompt-variables)

### Agent Prompting Guides
- [PromptHub: Prompt Engineering for AI Agents](https://www.prompthub.us/blog/prompt-engineering-for-ai-agents)
- [Prompting Guide: LLM Agents](https://www.promptingguide.ai/research/llm-agents)
- [Tool Calling with LLMs (PromptLayer)](https://blog.promptlayer.com/tool-calling-with-llms-how-and-when-to-use-it/)
