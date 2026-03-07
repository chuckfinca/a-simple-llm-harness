# Trends Scout: System Prompt Composition for LLM Agent Harnesses

Date: 2026-03-07

Research scope: How leading practitioners and companies organize system prompt
instructions when agents have multiple tool capabilities. Focused on what
people are actually doing in 2025-2026, not theoretical frameworks.

---

## Confirmed Trends (Multiple Sources, Real Adoption)

### 1. "Context Engineering" Has Replaced "Prompt Engineering" as the Core Discipline

**What it means practically:** Context engineering is not about finding clever
wording. It is about managing the entire information environment the model
operates in -- system prompt, tool definitions, conversation history,
retrieved documents, and external state. The system prompt is one component
of a larger context assembly pipeline.

Anthropic defines it as "the set of strategies for curating and maintaining
the optimal set of tokens during LLM inference, including all the other
information that may land there outside of the prompts." The shift is from
"what words do I use?" to "what information does the model need to see, in
what order, and what should be excluded?"

**What practitioners converge on:**

- The system prompt should contain "the minimal set of information that fully
  outlines expected behavior." Minimal does not mean short -- it means no
  unnecessary tokens. Start with a minimal prompt on the best model, then add
  instructions iteratively based on observed failure modes.
- Organize the prompt at the "right altitude" -- specific enough to guide
  behavior, flexible enough to let the model use judgment. Two failure modes:
  (a) brittle over-specification ("CRITICAL: YOU MUST call list_files FIRST")
  and (b) vague under-specification ("use tools when appropriate").
- Aggressive language ("CRITICAL!", "YOU MUST", "NEVER EVER") actively hurts
  newer Claude models. Use calm, direct instructions.

**Evidence of real adoption:**

- Anthropic's own engineering blog posts (three major articles in 2025)
  formalize this as the primary skill for harness builders.
- Manus AI rebuilt their agent 4 times and settled on context engineering as
  the core discipline, with KV-cache hit rate as their #1 production metric.
- Spotify credits context engineering as the key enabler for their "Honk"
  background coding agent project.
- LangChain formalized four context operations: write (persist externally),
  select (retrieve relevant), compress (summarize), isolate (separate per
  agent).

**Implications for our harness:** The `_workspace_context()` function in
`__main__.py` is already doing context engineering -- assembling prompt
sections conditionally at runtime. The question is how to scale this pattern
as capabilities grow.

Sources (with dates):
- [Anthropic -- Effective Context Engineering (2025)](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Manus -- Context Engineering Lessons (July 2025)](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [Spotify -- Context Engineering for Background Agents (Nov 2025)](https://engineering.atspotify.com/2025/11/context-engineering-background-coding-agents-part-2)
- [Addyo Substack -- Context Engineering: Bringing Engineering Discipline to Prompts](https://addyo.substack.com/p/context-engineering-bringing-engineering)
- [FlowHunt -- Context Engineering Guide 2025](https://www.flowhunt.io/blog/context-engineering/)

---

### 2. Modular Prompt Assembly Is the Standard Architecture

**What it is:** Instead of a single monolithic system prompt string, the
prompt is assembled from discrete, purpose-specific fragments at runtime.
Each fragment owns one concern (role, tool guidance, workspace context,
output format, safety rules).

**Who is doing this:**

**Claude Code** (Anthropic's own production agent) uses 110+ prompt
fragments conditionally assembled at startup. The base prompt is only ~269
tokens ("You are Claude Code, Anthropic's official CLI for Claude"). The
rest is loaded based on environment and configuration:

- Tool instructions: each of 18 builtin tools has its own description
  fragment (separate from the tool JSON schema)
- Coding guidelines, safety rules, response style guidance
- Environment context: working directory, OS, git status, shell type
- Project context: CLAUDE.md files loaded from filesystem hierarchy
- Subagent prompts: loaded only when plan/explore/task mode activates
- MCP tool descriptions: added as discrete blocks when servers connect

Fragment sizes range from 18 tokens (behavioral nudges) to 2,610 tokens
(security review blocks). The architecture uses conditional loading --
components are included only when the feature they describe is active.

**OpenAI Agents SDK** takes a simpler but similar approach: each Agent has
a `name`, `instructions` (system prompt), `model`, and `tools`. When agents
hand off to sub-agents, each sub-agent carries its own instructions. The
prompt is assembled per-agent, not globally.

**Smolagents** (HuggingFace) uses a template with five sections and a
`{{tool_descriptions}}` placeholder that gets filled with auto-generated
tool descriptions at runtime. The template is mandatory -- custom prompts
that omit the placeholder break the agent.

**Implications for our harness:** The current approach of `system_prompt +=
_workspace_context(workspace)` is the simplest form of modular assembly.
The natural evolution is to have each capability (file search, code execution,
spreadsheet analysis) contribute its own prompt section, assembled
conditionally based on what is configured.

Sources:
- [Claude Code System Prompts (Piebald-AI)](https://github.com/Piebald-AI/claude-code-system-prompts)
- [System Prompt Architecture (DeepWiki)](https://deepwiki.com/shanraisshan/claude-code-best-practice/8.4-system-prompt-architecture)
- [OpenAI Agents SDK Docs](https://openai.github.io/openai-agents-python/agents/)
- [Smolagents Guided Tour](https://huggingface.co/docs/smolagents/v0.1.3/en/guided_tour)

---

### 3. Markdown Is the De Facto Format for System Prompts

**The consensus:** Structured markdown with headers (`##`) is the dominant
format for system prompts in production. Not YAML, not XML, not plain text.

**Evidence:**

- Claude Code's system prompt uses markdown headers and lists throughout.
- Anthropic's own guidance recommends "XML tagging or Markdown headers" for
  section delineation, but in practice their own tools use markdown.
- CLAUDE.md, AGENTS.md, .cursorrules, .windsurfrules -- the entire ecosystem
  of agent instruction files uses markdown.
- Anthropic's Agent Skills use markdown for SKILL.md instruction files.
- Research shows markdown is the most token-efficient structured format
  compared to JSON, YAML, or XML, while maintaining clear hierarchy.

**Research on format performance:**

- GPT-3.5-turbo performance varies by up to 40% depending on prompt format,
  but GPT-4+ models are "more robust" to format differences.
- Markdown was "often optimal for GPT-4" in benchmarks.
- YAML slightly edges out markdown on accuracy in some tests, but markdown
  is more token-efficient.
- The practical conclusion: for frontier models, format matters less than
  content. Markdown wins on the combination of readability, token efficiency,
  and model familiarity.

**Why markdown specifically:**

- Models are trained on enormous amounts of markdown (GitHub, documentation),
  so they parse it natively.
- Headers create clear section boundaries without verbose delimiters.
- Lists encode sequential instructions naturally.
- Code blocks delineate examples from instructions.
- It is human-readable without tooling, making it debuggable.

**Implications for our harness:** Use markdown headers (`##`) to structure
prompt sections. The existing `_workspace_context()` already does this
(`"## Workspace"`, `"## Citing Sources"`). This is the right format.

Sources:
- [Does Prompt Formatting Impact LLM Performance? (arXiv)](https://arxiv.org/html/2411.10541v1)
- [Why Use Markdown in Your Agents' System Prompt? (Medium)](https://medium.com/@edprata/why-use-markdown-in-your-agents-system-prompt-41ad258a25c7)
- [Best Nested Data Format for LLMs](https://www.improvingagents.com/blog/best-nested-data-format/)
- [Structured Prompting: YAML, JSON, XML, or Plain Text?](https://felix-pappe.medium.com/structured-prompting-for-llms-from-raw-text-to-xml-daf39b461f13)

---

### 4. System Prompt Structure Must Be Cache-Friendly

**What it is:** Prompt caching stores the computational state of the
prompt prefix. If the prefix is identical across requests, the cache is
hit and you get 90% cost reduction and 85% latency reduction. If even a
single token changes in the prefix, the cache invalidates from that point
forward.

**What this means for prompt organization:**

The system prompt must be organized as **static-first, dynamic-last**.
Sections that never change go at the top. Sections that change per-session
go at the bottom. Sections that change per-request go in the conversation
messages, not the system prompt at all.

**Manus AI's production rules (battle-tested):**

1. Never put timestamps in the system prompt (kills cache on every request).
2. Keep tool definitions stable -- do not dynamically add/remove tools
   mid-session. Instead, mask unavailable tools at the token level.
3. Make conversation history append-only (never truncate from the middle).
4. Use deterministic serialization (`sort_keys=True` on JSON).
5. Place explicit cache breakpoints at the end of each static section.

**The ordering pattern that maximizes cache hits:**

```
[STATIC] Role and identity         -- never changes
[STATIC] Tool guidance             -- changes only when tools change
[STATIC] Output format rules       -- rarely changes
[SEMI]   Workspace/environment     -- changes per session, not per turn
[DYNAMIC] Conversation messages    -- changes every turn
```

**Implications for our harness:** The current design already separates
`LH_SYSTEM_PROMPT` (static) from `_workspace_context()` (semi-dynamic,
set once per session). This is correct. As we add more capability modules,
they should be ordered by stability: most-stable sections first, least-stable
last.

Sources:
- [Manus -- Context Engineering (July 2025)](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [Anthropic -- Prompt Caching](https://www.anthropic.com/news/prompt-caching)
- [Don't Break the Cache (arXiv, Jan 2026)](https://arxiv.org/html/2601.06007v2)
- [Prompt Caching: 60x Cost Reduction (Bugster)](https://newsletter.bugster.dev/p/prompt-caching-how-we-reduced-llm)
- [KV-Cache Aware Prompt Engineering](https://ankitbko.github.io/blog/2025/08/prompt-engineering-kv-cache/)

---

## Emerging Patterns (Early but Promising)

### 5. The "Skills" / Progressive Disclosure Pattern

**What it is:** Instead of loading all instructions for all capabilities
into the system prompt upfront, load only metadata (name + one-line
description) for each capability at startup. When the model decides it
needs a capability, it reads the full instructions from the filesystem
on demand.

**How Anthropic's Agent Skills work:**

Each skill is a directory containing a `SKILL.md` file with two parts:

1. **YAML frontmatter** (between `---` markers): `name`, `description`,
   and optional fields like `allowed-tools`, `model`, `when_to_use`.
2. **Markdown body**: Full instructions the model follows when the skill
   is invoked.

At startup, only the name and description from every installed skill are
pre-loaded into the system prompt (within a 15,000-character budget). This
gives the model a "table of contents" without consuming context on
instructions it may never need.

When a skill is triggered, the model uses bash to `cat` the SKILL.md file,
bringing the full instructions into the context window. If those instructions
reference other files (schemas, templates, scripts), the model reads those
too -- on demand, not upfront.

**Why this matters for growing prompt size:**

The progressive disclosure pattern directly addresses the "growing system
prompt" problem. Instead of the prompt growing linearly with each new
capability, only the metadata grows (at ~50 characters per skill). The full
instructions for each capability load only when needed, and only the
relevant supporting files load within those instructions.

A harness with 20 capabilities might have 1,000 characters of skill metadata
in its system prompt instead of 20,000 characters of full instructions.

**Who is doing this:**

- Anthropic: Agent Skills are a first-class feature of the Claude API and
  Claude Code, with official documentation and SDK support.
- Claude Code itself uses this pattern for its Plan, Explore, and Task
  sub-agents -- each has its own prompt that loads only when that mode
  activates.

**Risk that it is hype:** Low. This is Anthropic's own production pattern,
used in Claude Code which is one of the most-used AI tools. The pattern is
also just good software engineering (lazy loading, separation of concerns).

**Implications for our harness:** This is directly relevant. As we add file
search, spreadsheet analysis, etc., each capability could be a "module"
with:
- A brief description loaded into the system prompt at startup
- Full instructions in a separate markdown file, read on demand

However, the full Agent Skills pattern requires the model to have filesystem
access (to read SKILL.md files). A simpler version for our harness: load
each capability's full instructions at startup but from separate files,
conditionally included based on configuration.

Sources:
- [Anthropic -- Agent Skills (Oct 2025)](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [Anthropic -- Agent Skills API Docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Claude Skills Architecture Decoded (Medium, Jan 2026)](https://medium.com/aimonks/claude-skills-architecture-decoded-from-prompt-engineering-to-context-engineering-a6625ddaf53c)
- [Claude Skills Deep Dive](https://leehanchung.github.io/blogs/2025/10/26/claude-skills-deep-dive/)

---

### 6. File-Based Prompt Templates (Markdown Files) over Code-Based Strings

**What it is:** Storing prompt instructions in separate `.md` files on the
filesystem rather than as Python string literals in source code.

**The emerging consensus:**

The ecosystem is converging on file-based prompts as the default. The
evidence comes from multiple independent sources:

- **CLAUDE.md** (Anthropic): Project-level instructions stored as a markdown
  file in the repo root. Read at session startup. Versioned with git.
- **AGENTS.md**: A cross-tool convention (works with Cursor, Claude Code,
  GitHub Copilot) for machine-readable project instructions. Markdown file,
  versioned in the repo.
- **.cursorrules / .windsurfrules**: IDE-specific instruction files, but
  the pattern is the same -- filesystem-based, versioned, separate from code.
- **SKILL.md** (Anthropic): Capability-specific instructions as markdown
  files in a known directory structure.
- **12-Factor Agents (Factor 2: "Own Your Prompts")**: "Version-control
  your prompts and prompt templates, expose them for easy editing, and
  avoid opaque prompt engineering libraries that hide prompt details."

**Why file-based over code-based:**

1. **Editability**: Non-engineers (product managers, domain experts) can
   edit markdown files. They cannot comfortably edit Python string literals
   with escape characters and concatenation.
2. **Version control**: Prompt changes show up as clean diffs in git.
   Changes to Python strings are harder to review because of escaping noise.
3. **Testability**: You can write evals that load a prompt file and test
   it against a suite of inputs. Changing the prompt is just changing the
   file, with no code changes needed.
4. **Separation of concerns**: The prompt (what the model should do) is
   separate from the harness code (how the model is called). This is the
   same principle as separating HTML templates from application code.
5. **Token inspection**: You can count tokens in a markdown file easily.
   Counting tokens in a Python string literal that spans 40 lines with
   concatenation and f-strings is error-prone.

**The practical pattern:**

```
src/
  llm_harness/
    prompts/
      role.md              # Static: identity and general behavior
      workspace.md         # Template: workspace-specific guidance
      search_strategy.md   # Static: how to search effectively
      citations.md         # Static: citation format rules
    __main__.py            # Assembles prompt from files at runtime
```

Each `.md` file is a self-contained prompt section. The harness reads them
at startup and concatenates them, with optional template variables
(`{file_count}`, `{workspace_path}`) filled in at runtime.

**What this is NOT:** This is not about using a templating engine like
Jinja2 (which adds complexity). It is about loading raw markdown files with
minimal string substitution. Python's `str.format()` or simple `replace()`
is sufficient.

**Risk that it is hype:** Very low. This is the pattern every major AI
coding tool has independently converged on. The disagreement is only about
details (file naming, directory structure), not the fundamental approach.

**Implications for our harness:** The current `_workspace_context()` function
returns a Python string literal with embedded markdown. This should migrate
to loading from a file. The search strategy instructions and citation format
rules would be separate files that are included when `LH_WORKSPACE` is
configured.

Sources:
- [12-Factor Agents -- Factor 2: Own Your Prompts](https://github.com/humanlayer/12-factor-agents/blob/main/content/factor-02-own-your-prompts.md)
- [How to Teach Your Coding Agent with AGENTS.md](https://ericmjl.github.io/blog/2025/10/4/how-to-teach-your-coding-agent-with-agentsmd/)
- [Claude Code Rules Directory](https://claude-blog.setec.rs/blog/claude-code-rules-directory)
- [Modular Prompt Engineering Best Practices 2026](https://chatpromptgenius.com/modular-prompt-engineering-best-practices-for-2026/)

---

## Things Becoming Obsolete

### Monolithic System Prompt Strings in Application Code

**What is going away:** Hardcoding the entire system prompt as a single
Python string literal (or environment variable) that grows as capabilities
are added.

**What is replacing it:** Modular prompt assembly from separate files, with
conditional inclusion based on configuration.

**Why:** A 2,000-token system prompt embedded in code becomes an
"unreadable wall of text that developers dread touching." Simple updates
require reviewing the entire prompt to avoid breaking hidden dependencies.
Every capability addition makes the string longer and harder to maintain.

**Timeline:** Already happening. The pattern shift is complete in production
tools (Claude Code, Cursor, etc.). Application harnesses are catching up.

### Framework-Managed Prompt Templates

**What is going away:** LangChain-style `PromptTemplate` objects that
hide the actual prompt behind abstraction layers.

**What is replacing it:** Direct ownership of prompt text, stored as
files, version-controlled, and assembled with simple string operations.

**Why:** 12-Factor Agents codified what practitioners discovered: "If the
agent gives a bad answer, you need to dive into the prompt and adjust it
like a piece of code." Abstraction layers that hide the prompt make this
impossible. The debugging advantage of seeing your exact prompt text
outweighs any convenience from template abstractions.

**Timeline:** Already well underway. Even LangChain's own team recommends
LangGraph (which gives more control) over LangChain classic.

Sources:
- [12-Factor Agents](https://github.com/humanlayer/12-factor-agents)
- [LangChain Blog -- Rise of Context Engineering](https://blog.langchain.com/the-rise-of-context-engineering/)
- [Long System Prompts Hurt Context Windows (Medium)](https://medium.com/data-science-collective/why-long-system-prompts-hurt-context-windows-and-how-to-fix-it-7a3696e1cdf9)

---

## Practitioner Convergence Points

### Convergence 1: Two Layers of Tool Guidance (Schema + Prompt)

Every production system examined uses both:

1. **Tool schemas** (the JSON in the `tools` parameter): Define the API
   contract -- what arguments a tool takes, their types, a description.
2. **System prompt guidance**: Describes when/why/in what order to use
   tools, and what environment they operate against.

Schemas tell the model HOW to call a tool. The system prompt tells the
model WHEN and WHY. Neither is sufficient alone.

Anthropic states: "tool descriptions and specs should be given just as
much prompt engineering attention as your overall prompts." They showed
that refining tool descriptions alone moved Claude Sonnet 3.5 to
state-of-the-art on SWE-bench Verified.

This is independently confirmed by Claude Code (tool descriptions as
separate markdown fragments in addition to schemas), Smolagents (mandatory
`{{tool_descriptions}}` placeholder in prompt), and OpenAI (each agent
carries its own `instructions` alongside its `tools`).

### Convergence 2: Filesystem as Prompt Extension

Multiple teams independently converge on using the filesystem to extend
the prompt without consuming the context window:

- **Claude Code**: CLAUDE.md files at multiple directory levels, loaded
  at session start.
- **Anthropic long-running agents**: claude-progress.txt and
  feature_list.json as external memory that agents read on demand.
- **Agent Skills**: SKILL.md files on the filesystem, read when needed.
- **Cursor/Windsurf**: .cursorrules / .windsurfrules files in the project.
- **Aider**: Auto-generated repo map file injected into context.

The pattern: keep the system prompt lean, but give the model access to
read additional instructions from files when it needs them.

### Convergence 3: The 4-Section Prompt Structure

Multiple sources independently arrive at roughly the same prompt structure:

1. **Role/Identity**: Who the agent is, one to two sentences.
2. **Capabilities/Tools**: What tools are available, when to use each.
3. **Environment/Context**: What workspace or data the agent has access to.
4. **Output Format/Rules**: How to format responses, cite sources, etc.

Variations on this appear in Anthropic's guidance ("instructions, context,
task, output"), IBM's "Cognitive Tools" pattern, the 4-block pattern
documented in multiple prompt engineering guides, and Smolagents' five
sections (introduction, tool descriptions, output format, rules,
authorization).

### Convergence 4: Start Minimal, Add Instructions Based on Failures

Both Anthropic and the 12-Factor Agents community arrive at the same
development methodology:

1. Start with the simplest possible prompt.
2. Run it against real tasks.
3. Identify specific failure modes.
4. Add targeted instructions to address those failures.
5. Re-test to confirm the fix does not cause regressions.

This is test-driven prompt development. It avoids the common failure of
pre-loading the prompt with speculative instructions that add tokens
without adding value.

Sources:
- [Anthropic -- Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Anthropic -- Writing Tools for Agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Anthropic -- Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [12-Factor Agents](https://github.com/humanlayer/12-factor-agents)
- [Smolagents Guided Tour](https://huggingface.co/docs/smolagents/v0.1.3/en/guided_tour)

---

## Warnings and Pitfalls

### 1. Do Not Over-Prompt

Anthropic explicitly warns that aggressive tool-use instructions hurt newer
Claude models. "CRITICAL: YOU MUST USE list_files FIRST" produces worse
behavior than "Start by listing files to see what is available." LLM
reasoning performance starts degrading around 3,000 system prompt tokens,
with the practical sweet spot for most tasks being 150-300 words of
instructions.

### 2. Do Not Duplicate Tool Schema Content in the Prompt

The system prompt should describe WHEN and WHY to use tools. It should NOT
re-describe WHAT arguments each tool takes -- that is the schema's job.
Duplicating this information wastes tokens and creates maintenance burden
when schemas change.

### 3. Do Not Use Dynamic Timestamps in System Prompts

This is the most common cache-killing mistake. A timestamp at the start of
the system prompt invalidates the entire prompt cache on every request. If
you need the model to know the current time, provide a `get_current_time`
tool or put the timestamp at the very end of the system prompt (after all
static content).

### 4. Do Not Over-Invest in Templating Infrastructure

Simple string substitution (`str.format()`) is sufficient for prompt
templates. Jinja2, custom DSLs (like POML), and framework-specific
template objects add complexity without proportional value. The prompts
themselves change far more often than the templating logic, so keep the
templating minimal and the prompts accessible.

### 5. The 10,000-Token Prompt Maintenance Problem

"A 10,000-token prompt becomes an unreadable wall of text that developers
dread touching. Simple updates require careful review of the entire prompt
to avoid breaking hidden dependencies." The modular file-based approach
directly addresses this -- each file is small, focused, and independently
editable.

Sources:
- [Anthropic -- Prompting Best Practices](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices)
- [Long System Prompts Hurt Context Windows (Medium)](https://medium.com/data-science-collective/why-long-system-prompts-hurt-context-windows-and-how-to-fix-it-7a3696e1cdf9)
- [Manus -- Context Engineering](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)

---

## Concrete Recommendation for This Harness

### Current State

The harness currently uses:
- `LH_SYSTEM_PROMPT` environment variable for the base prompt (static)
- `_workspace_context()` in `__main__.py` to append workspace + search
  strategy + citation instructions (semi-dynamic, assembled at startup)

This is a Python string literal spanning ~40 lines with escape characters,
concatenation, and embedded markdown. It works but does not scale.

### Recommended Architecture

**Phase 1: Extract prompt sections into markdown files.**

```
src/llm_harness/prompts/
    search_strategy.md     # When searching the workspace...
    citations.md           # How to cite sources...
    workspace.md           # Template: You have access to a workspace...
```

The harness reads these files and assembles them at startup. Each file is a
self-contained prompt section with a `##` header. Template variables
(`{file_count}`) are substituted with `str.format()`.

The `_workspace_context()` function becomes a `build_system_prompt()`
function that:

1. Reads the base prompt from `LH_SYSTEM_PROMPT` (or a default file).
2. If `LH_WORKSPACE` is configured, reads and appends `workspace.md`,
   `search_strategy.md`, and `citations.md` with template variables filled.
3. Returns the assembled string.

**Phase 2: Add capability modules.**

When adding spreadsheet analysis or other capabilities:

```
src/llm_harness/prompts/
    search_strategy.md
    citations.md
    workspace.md
    spreadsheet.md         # New: when to use spreadsheet tools
    code_execution.md      # New: guidance for run_python
```

Each capability registers its prompt file. The assembly function includes
only the files for configured capabilities. This is conditional assembly
at the simplest possible level -- no framework, no registry, just "if this
capability is active, include its prompt file."

**Phase 3 (if needed): Progressive disclosure.**

If the combined prompt exceeds ~2,000 tokens and some capabilities are
rarely used, consider the Skills pattern: load only metadata (name +
description) at startup, and have the model read full instructions from
a file on demand. This requires the model to have a tool for reading
prompt files, which is a more significant architectural change.

### What This Looks Like in Code

The assembly function is straightforward:

```python
def build_system_prompt(
    base_prompt: str,
    workspace: Path | None = None,
) -> str:
    sections = [base_prompt]

    if workspace:
        prompts_dir = Path(__file__).parent / "prompts"
        for name in ["workspace", "search_strategy", "citations"]:
            path = prompts_dir / f"{name}.md"
            template = path.read_text()
            section = template.format(
                file_count=count_files(workspace),
                workspace_path=str(workspace),
            )
            sections.append(section)

    return "\n\n".join(sections)
```

### Why This Design

1. **Prompt text is in markdown files** -- editable, diffable, testable.
2. **Assembly logic is minimal Python** -- `read_text()` + `str.format()`
   + `join()`. No framework, no template engine.
3. **Sections are independent** -- each file stands alone. Adding a new
   capability means adding a new file and a conditional include.
4. **Cache-friendly** -- static sections come first, workspace-specific
   sections come last. The order maximizes prompt cache hit rate.
5. **Scales without growing complexity** -- 3 capabilities or 30, the
   pattern is the same. Only the number of files grows.

---

## Open Questions

### 1. Where Should the Base System Prompt Live?

Currently `LH_SYSTEM_PROMPT` is an environment variable. Should it be:
- An environment variable (current -- flexible but not versioned)?
- A default markdown file in the package (versioned, but less flexible)?
- Both (file as default, env var as override)?

The ecosystem leans toward "file as default, override mechanism available."
CLAUDE.md is a file with the ability to override via settings.

### 2. How to Handle Model-Specific Prompt Variations

Different models respond differently to prompt formatting. Claude prefers
XML tags for data sections; GPT models are more format-agnostic. If the
harness supports multiple models via LiteLLM, should prompt files vary
per model? The current evidence suggests this is not worth the complexity
for frontier models, which are increasingly robust to format differences.

### 3. When Does Progressive Disclosure Become Worth the Complexity?

The Skills pattern (load instructions on demand) adds real value when:
- There are 10+ capability modules
- Most queries only need 1-2 capabilities
- The full prompt would exceed ~3,000 tokens

For our harness with 3-5 capabilities, full assembly at startup is simpler
and sufficient. The trip wire for progressive disclosure is when the
assembled prompt starts hurting performance or cost.

### 4. Prompt Versioning and Eval Integration

If prompts are in files, should they be versioned independently of the
code? Should prompt changes trigger eval runs? The 12-Factor Agents
community says yes: "build tests and evaluations for your input prompts
as you would for any other code." This is an area where tooling (Langfuse,
Braintrust) is maturing but not yet standardized.

---

## Summary: The Five Patterns to Adopt

1. **File-based prompt modules.** Move prompt sections from Python string
   literals to markdown files. Each file owns one concern.

2. **Conditional assembly.** Include prompt sections based on which
   capabilities are configured. Static sections first, dynamic last.

3. **Two layers of tool guidance.** Tool schemas define the API. The system
   prompt defines the strategy (when, why, what order).

4. **Minimal templating.** Use `str.format()` for template variables.
   No Jinja2, no custom DSLs, no framework abstractions.

5. **Iterative prompt development.** Start minimal, test against real
   tasks, add instructions only to fix observed failures.

---

## All Sources

### Anthropic Engineering (Primary)
- [Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Writing Effective Tools for AI Agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Equipping Agents with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [Building Effective AI Agents](https://www.anthropic.com/research/building-effective-agents)
- [Agent Skills API Docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
- [Prompting Best Practices](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices)
- [Prompt Caching](https://www.anthropic.com/news/prompt-caching)

### Claude Code Architecture
- [Claude Code System Prompts (Piebald-AI)](https://github.com/Piebald-AI/claude-code-system-prompts)
- [System Prompt Architecture (DeepWiki)](https://deepwiki.com/shanraisshan/claude-code-best-practice/8.4-system-prompt-architecture)
- [Claude Skills Deep Dive](https://leehanchung.github.io/blogs/2025/10/26/claude-skills-deep-dive/)
- [Claude Skills Architecture Decoded (Medium)](https://medium.com/aimonks/claude-skills-architecture-decoded-from-prompt-engineering-to-context-engineering-a6625ddaf53c)
- [Modular Rules in Claude Code](https://claude-blog.setec.rs/blog/claude-code-rules-directory)

### Prompt Format Research
- [Does Prompt Formatting Impact LLM Performance? (arXiv)](https://arxiv.org/html/2411.10541v1)
- [Best Nested Data Format for LLMs](https://www.improvingagents.com/blog/best-nested-data-format/)
- [Structured Prompting: YAML, JSON, XML, or Plain Text?](https://felix-pappe.medium.com/structured-prompting-for-llms-from-raw-text-to-xml-daf39b461f13)

### Context Engineering
- [Manus -- Context Engineering Lessons (July 2025)](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
- [Spotify -- Context Engineering (Nov 2025)](https://engineering.atspotify.com/2025/11/context-engineering-background-coding-agents-part-2)
- [FlowHunt -- Context Engineering Guide](https://www.flowhunt.io/blog/context-engineering/)
- [Addyo -- Context Engineering](https://addyo.substack.com/p/context-engineering-bringing-engineering)

### Prompt Caching
- [Don't Break the Cache (arXiv, Jan 2026)](https://arxiv.org/html/2601.06007v2)
- [Prompt Caching: 60x Cost Reduction (Bugster)](https://newsletter.bugster.dev/p/prompt-caching-how-we-reduced-llm)
- [KV-Cache Aware Prompt Engineering](https://ankitbko.github.io/blog/2025/08/prompt-engineering-kv-cache/)

### Practitioner Frameworks
- [12-Factor Agents](https://github.com/humanlayer/12-factor-agents)
- [12-Factor Agents -- Factor 2: Own Your Prompts](https://github.com/humanlayer/12-factor-agents/blob/main/content/factor-02-own-your-prompts.md)
- [Smolagents Guided Tour](https://huggingface.co/docs/smolagents/v0.1.3/en/guided_tour)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/agents/)
- [How to Teach Your Coding Agent with AGENTS.md](https://ericmjl.github.io/blog/2025/10/4/how-to-teach-your-coding-agent-with-agentsmd/)

### Prompt Size and Maintenance
- [Long System Prompts Hurt Context Windows (Medium)](https://medium.com/data-science-collective/why-long-system-prompts-hurt-context-windows-and-how-to-fix-it-7a3696e1cdf9)
- [PromptLayer -- Disadvantage of Long Prompts](https://blog.promptlayer.com/disadvantage-of-long-prompt-for-llm/)
- [Managing Token Budgets for Complex Prompts](https://apxml.com/courses/getting-started-with-llm-toolkit/chapter-3-context-and-token-management/managing-token-budgets)
