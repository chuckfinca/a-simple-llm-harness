# Research: Modular System Prompt Composition

Date: 2026-03-07

## The Problem

The harness currently assembles system prompts via a single function
`_workspace_context()` that returns a ~40-line string appended to a base
prompt from `LH_SYSTEM_PROMPT`. As we add more capabilities (spreadsheet
search, code execution guidance, new tool families), this approach will not
scale. We need a pattern for managing prompt "modules" -- discrete blocks of
instructions that can be independently authored, conditionally included, and
composed into a coherent system prompt at runtime.

---

## 1. How Production Systems Compose System Prompts

### Pattern A: Conditional String Assembly (Claude Code, OpenCode)

Claude Code uses 110+ individual prompt strings that are conditionally
assembled at runtime from a large minified JS file. The architecture works
as follows:

1. A small base prompt establishes identity (~269 tokens).
2. Environment context is injected: working directory, OS, git status, shell.
3. Each of the 18 builtin tools has a dedicated markdown description that is
   loaded into the system prompt text -- separate from the tool JSON schemas.
4. Conditional sections are included based on feature flags, configuration,
   and environment (e.g., plan mode prompts, permission descriptions, sub-agent
   descriptions).
5. CLAUDE.md files from the project are loaded as user context.
6. A plugin hook allows plugins to mutate the prompt array post-assembly.

OpenCode follows the same pattern: an orchestrator module
(`packages/opencode/src/session/prompt.ts`) runs on each loop iteration and
asks two sub-modules for content: `system.ts` provides environment context and
selects a provider-specific prompt file (anthropic.txt, beast.txt, gemini.txt),
while `instruction.ts` walks the filesystem for AGENTS.md / CLAUDE.md files.

**Key insight**: Both systems treat the prompt as a list of sections that get
joined. Sections are plain strings (or markdown files on disk). The assembly
logic is regular code with `if` statements -- no template engine needed.

Sources:
- [Claude Code System Prompts (Piebald-AI)](https://github.com/Piebald-AI/claude-code-system-prompts)
- [OpenCode Prompt Construction (Gist)](https://gist.github.com/rmk40/cde7a98c1c90614a27478216cc01551f)
- [System Prompt Architecture (DeepWiki)](https://deepwiki.com/shanraisshan/claude-code-best-practice/8.4-system-prompt-architecture)

### Pattern B: Decorator-Based Dynamic Prompts (Pydantic AI)

Pydantic AI uses a decorator pattern where system prompt functions are
registered on an agent and called at runtime:

```python
agent = Agent(
    'openai:gpt-4o',
    deps_type=str,
    system_prompt="Use the customer's name while replying to them.",
)

@agent.system_prompt
def add_the_users_name(ctx: RunContext[str]) -> str:
    return f"The user's name is {ctx.deps}."

@agent.system_prompt
def add_the_date() -> str:
    return f'The date is {date.today()}.'
```

Static and dynamic prompts are appended **in registration order** at runtime.
Dynamic prompts receive a `RunContext` with dependency injection, so they can
access runtime state (database connections, user info, configuration).

**Key insight**: Each prompt contributor is a standalone function. Functions
are registered declaratively and composed automatically. This is the cleanest
API for prompt composition in a Python codebase -- but it requires buying into
the Pydantic AI agent abstraction.

Source:
- [Pydantic AI Agents](https://ai.pydantic.dev/agent/)

### Pattern C: Progressive Loading / Lazy Injection (Claude Code Skills)

Claude Code's Skills system demonstrates a different approach: **deferred
prompt loading**. At startup, only skill metadata (name + description from
YAML frontmatter) is loaded into the system prompt. The full skill
instructions (SKILL.md) are loaded on-demand when the skill becomes relevant:

1. Startup: Load name + description from all skills' YAML frontmatter into
   the system prompt.
2. Trigger: When a skill is relevant, Claude reads the SKILL.md file via
   bash, bringing full instructions into the context window.
3. Cascade: If SKILL.md references other files (FORMS.md, schemas), Claude
   reads those too.

This is progressive disclosure for prompts. The system prompt stays small,
and detailed instructions only enter context when needed. The tradeoff is
that instructions arrive as user/assistant messages (via tool results) rather
than in the system prompt, which may reduce their authority for some models.

Sources:
- [Claude Code Skills Docs](https://code.claude.com/docs/en/skills)
- [Claude Agent Skills Deep Dive](https://leehanchung.github.io/blogs/2025/10/26/claude-skills-deep-dive/)
- [Inside Claude Code Skills (Mikhail Shilkov)](https://mikhail.io/2025/10/claude-code-skills/)

### Pattern D: Template Placeholders (Smolagents, Jinja2)

Smolagents uses a template with `{{tool_descriptions}}` placeholders. At
agent initialization, tool metadata is extracted and formatted into a
description block that replaces the placeholder. The template has five fixed
sections (introduction, tool descriptions, output format, rules, authorization).

Jinja2 is the most common template engine for this pattern. It supports
conditionals (`{% if workspace %}...{% endif %}`), loops, and filters.
Microsoft's Semantic Kernel uses Jinja2 prompt templates, and LangChain
supports Jinja2 as an alternative to f-strings.

**Key insight**: Jinja2 adds power (loops, conditionals, includes) but also
adds a dependency, a separate file type to maintain, and a security surface
(Jinja2 templates from untrusted sources can execute arbitrary code). For
most custom harnesses, Python's own string formatting is sufficient and safer.

Sources:
- [Smolagents Guided Tour](https://huggingface.co/docs/smolagents/v0.1.3/en/guided_tour)
- [PromptLayer: Prompt Templates with Jinja2](https://blog.promptlayer.com/prompt-templates-with-jinja2-2/)
- [LangChain warns against untrusted Jinja2 templates](https://mirascope.com/blog/langchain-prompt-template)

### Pattern E: File-Based Modular Prompts (Manus, Clawdbot)

Some production agents split behavior across multiple markdown files on disk:

- **Manus**: AgentLoop.txt, Modules.md, tools.json
- **Clawdbot**: SOUL.md (personality/voice), AGENTS.md (operational rules),
  IDENTITY.md (privacy boundaries)

Each file has a single responsibility. The assembly code reads each file and
concatenates them. This pattern treats prompts as documentation -- they can be
edited by non-engineers, diffed in git, and reviewed in PRs.

Source:
- [awesome-ai-system-prompts](https://github.com/dontriskit/awesome-ai-system-prompts)

---

## 2. What Format Works Best for Prompt Templates

### The Options

| Format | Pros | Cons |
|--------|------|------|
| Python strings (f-strings, `.format()`) | Zero dependencies, type-checked, IDE support, easy debugging | Templates mixed with code, harder for non-engineers to edit |
| Python functions returning strings | Same as above + conditional logic is natural, testable | Same as above |
| Markdown files on disk | Easy to edit, git-diffable, readable by non-engineers, separates content from code | Need file I/O, no type checking on variables, harder to debug |
| Jinja2 templates | Conditionals/loops in templates, includes, filters | Extra dependency, security risk from untrusted templates, learning curve |
| YAML/JSON with string values | Structured, easy to parse | Awkward for long text, quoting issues |

### What Real Projects Choose

**Claude Code**: Plain strings in TypeScript/JavaScript. The 110+ prompt
fragments are string literals in source code and `.txt` files on disk.

**OpenCode**: Static `.txt` files on disk for provider-specific prompts.
Regular TypeScript code for dynamic assembly.

**Pydantic AI**: Python functions returning strings.

**Smolagents**: Python string with `{{placeholder}}` syntax (not full Jinja2).

**Banks (open-source library)**: Jinja2 templates with LLM-specific
extensions. Explicitly designed for prompt management with version control.

### Recommendation for This Harness

**Python functions returning strings** is the right choice for a minimal
harness. Reasons:

1. Zero new dependencies.
2. Each function is independently testable.
3. Conditional logic uses regular Python -- no template DSL to learn.
4. IDE support (type checking, autocomplete, refactoring) works out of the box.
5. Functions compose naturally: the assembler calls each function and joins.

If prompt content grows large enough that non-engineers need to edit it,
consider **markdown files on disk** loaded by Python functions. This is the
pattern Claude Code and OpenCode use for their longer prompt sections. The
function handles the loading and any variable substitution; the file holds
the prose.

The threshold for moving to files: when a prompt section exceeds ~30 lines
or when someone other than the developer needs to edit it.

Sources:
- [Banks: LLM prompt language based on Jinja](https://github.com/masci/banks)
- [Latitude: Reusable Prompts](https://latitude.so/blog/reusable-prompts-structured-design-frameworks)

---

## 3. How to Handle Conditional Prompt Assembly

### The Simple Pattern: List + Filter + Join

Every production system examined uses a variation of this pattern:

```python
def build_system_prompt(config: Config) -> str:
    sections: list[str] = []

    sections.append(base_identity())

    if config.workspace:
        sections.append(workspace_instructions(config.workspace))

    if config.spreadsheets:
        sections.append(spreadsheet_instructions())

    if config.code_execution:
        sections.append(code_execution_instructions())

    sections.append(citation_instructions())

    return "\n\n".join(sections)
```

This is what Claude Code does (at scale, with 110+ sections). This is what
OpenCode does. This is effectively what Pydantic AI's decorator system
compiles down to.

**Why this works**:
- Adding a new capability = writing one function + one `if` block.
- Removing a capability = deleting the `if` block.
- Reordering = moving lines.
- Testing = calling individual functions and checking their output.
- Debugging = printing the final joined string.

### The Registration Pattern (More Structured)

For harnesses with many capabilities, a registration pattern avoids a
growing `if/elif` chain:

```python
from dataclasses import dataclass
from typing import Callable

@dataclass
class PromptSection:
    name: str
    builder: Callable[[Config], str | None]
    order: int = 0

_registry: list[PromptSection] = []

def register_prompt_section(name: str, order: int = 0):
    def decorator(fn: Callable[[Config], str | None]):
        _registry.append(PromptSection(name=name, builder=fn, order=order))
        return fn
    return decorator

@register_prompt_section("workspace", order=10)
def workspace_instructions(config: Config) -> str | None:
    if not config.workspace:
        return None
    return f"## Workspace\n\nYou have access to ..."

def build_system_prompt(config: Config) -> str:
    sections = sorted(_registry, key=lambda s: s.order)
    parts = [s.builder(config) for s in sections]
    return "\n\n".join(p for p in parts if p is not None)
```

Each capability module registers its own prompt section. The assembler
collects them, sorts by order, filters out `None` returns (capability not
active), and joins.

**When to use this**: When you have 5+ capabilities and want to keep each
capability's prompt logic co-located with its tool definitions. This is
essentially what Pydantic AI's `@agent.system_prompt` decorator does, but
without the framework.

**When the simple pattern is better**: When you have 2-4 capabilities and
want maximum readability. The explicit list is easier to understand than
a registry with implicit ordering.

---

## 4. Architectural Patterns for Prompt Modules

### Pattern 1: Capability Modules (Recommended for This Harness)

Each capability is a Python module that exports three things:

1. **Tool definitions** (the JSON schemas for the API)
2. **Tool implementations** (the functions that execute)
3. **Prompt instructions** (a function returning the system prompt section)

```
src/llm_harness/
    capabilities/
        __init__.py          # exports build_system_prompt()
        workspace.py         # workspace tools + prompt section
        spreadsheet.py       # spreadsheet tools + prompt section
        code_execution.py    # run_python tool + prompt section
        calculator.py        # calculator tool + prompt section
```

Each capability module looks like:

```python
# capabilities/workspace.py

TOOL_DEFINITIONS = [...]  # list_files, search_files, read_file schemas

def execute(name: str, args: dict) -> str:
    ...  # tool dispatch

def prompt_section(workspace: Path) -> str:
    file_count = sum(1 for p in workspace.rglob("*") if p.is_file())
    return (
        "## Workspace\n\n"
        f"You have access to a workspace directory containing {file_count} "
        "text documents. Use list_files, search_files, and read_file to "
        "explore them.\n\n"
        "When searching the workspace:\n"
        "- Extract key nouns from the question...\n"
        ...
    )
```

The assembler collects tool definitions and prompt sections from all active
capabilities:

```python
# capabilities/__init__.py

def build_system_prompt(config: Config) -> str:
    sections = [base_prompt()]

    if config.workspace:
        sections.append(workspace.prompt_section(config.workspace))
    if config.spreadsheets:
        sections.append(spreadsheet.prompt_section(config.spreadsheets))

    sections.append(citation_instructions())
    return "\n\n".join(sections)

def collect_tool_definitions(config: Config) -> list[dict]:
    tools = []
    tools.extend(calculator.TOOL_DEFINITIONS)
    tools.extend(time.TOOL_DEFINITIONS)
    if config.workspace:
        tools.extend(workspace.TOOL_DEFINITIONS)
    if config.spreadsheets:
        tools.extend(spreadsheet.TOOL_DEFINITIONS)
    return tools
```

**Why this pattern wins**: Tool definitions, implementations, and prompt
instructions are co-located. When you add a new capability, you write one
module. When you remove one, you delete one module and one `if` block. The
prompt and the tools always stay in sync because they live in the same file.

### Pattern 2: Prompt Files on Disk

For teams where prompts are edited frequently or by non-engineers:

```
prompts/
    base.md
    workspace.md
    spreadsheet.md
    citation.md
```

Each file is a complete prompt section in markdown. The assembler reads
and concatenates:

```python
def build_system_prompt(config: Config) -> str:
    sections = [_load_prompt("base")]

    if config.workspace:
        content = _load_prompt("workspace")
        content = content.replace("{file_count}", str(count_files(config.workspace)))
        sections.append(content)

    return "\n\n".join(sections)

def _load_prompt(name: str) -> str:
    path = Path(__file__).parent / "prompts" / f"{name}.md"
    return path.read_text()
```

**Tradeoff**: Prompts are easy to read and edit, but variable substitution
is manual (find/replace or f-string formatting on the loaded text). This
is the approach Claude Code uses for its larger prompt sections and tool
descriptions.

### Pattern 3: Hybrid (Functions + Files for Long Sections)

The practical middle ground: short prompt sections live as Python strings
in the capability module. Long prompt sections (like detailed search strategy
guidance or citation rules) live in markdown files loaded by the capability
module.

```python
# capabilities/workspace.py

_SEARCH_STRATEGY = (Path(__file__).parent / "prompts" / "search_strategy.md").read_text()

def prompt_section(workspace: Path) -> str:
    file_count = sum(1 for p in workspace.rglob("*") if p.is_file())
    return (
        "## Workspace\n\n"
        f"You have access to {file_count} documents.\n\n"
        f"{_SEARCH_STRATEGY}\n\n"
    )
```

This keeps the dynamic parts (file count, workspace path) in Python and the
static prose in editable markdown files.

---

## 5. Claude Code's Skills: What to Adopt, What to Skip

### What the Skills System Does

Claude Code Skills are markdown files (SKILL.md) with YAML frontmatter that
live on the filesystem. The architecture:

1. **Metadata loading at startup**: Only the `name` and `description` from
   YAML frontmatter are loaded into the system prompt. This keeps the
   startup prompt small.
2. **On-demand full loading**: When a skill is triggered, Claude uses bash
   to read the SKILL.md file, bringing full instructions into the context
   window as a tool result message.
3. **Cascading references**: SKILL.md can reference other files (schemas,
   forms, scripts). Claude reads these as needed.

### What to Adopt

**The metadata-first pattern**: For capabilities that are large and
infrequently used, include only a brief description in the system prompt
and load full instructions on demand. This is relevant when we have 10+
capabilities and the system prompt would otherwise exceed 2000+ tokens.

**The YAML frontmatter convention**: Storing structured metadata (name,
description, when to activate) alongside the prose instructions in a
single file is clean and self-documenting.

### What to Skip

**The full meta-tool architecture**: Skills use a `Skill` tool that acts
as a dispatcher, injecting instructions as hidden user messages. This is
overkill for a harness with 3-6 capabilities. Direct conditional assembly
is simpler and gives instructions system-prompt-level authority.

**The progressive loading via bash reads**: For a simple harness, all
prompt sections should be in the system prompt. Loading instructions via
tool calls works when you have 50+ skills and need to keep the prompt
small, but it reduces instruction authority (system prompt > user message
> tool result for most models).

---

## 6. Framework Patterns Worth Stealing

### From Pydantic AI: Ordered Prompt Functions with Dependency Injection

The `@agent.system_prompt` decorator pattern is the cleanest API for
modular prompt composition. The key ideas we can adopt without the framework:

1. Prompt sections are **functions that return strings**.
2. Functions are called **at runtime**, not at import time.
3. Functions receive **context** (config, workspace path, etc.).
4. Functions return **None to opt out** (capability not active).
5. Results are **joined in registration order**.

### From DSPy: Separation of Specification and Implementation

DSPy Signatures declare *what* a task should do, not *how* to prompt for it.
While this level of abstraction is overkill for system prompt composition,
the principle applies: each prompt section should specify the capability's
**intent and constraints**, not micro-manage the model's behavior.

Good: "Search before reading. Do not read files sequentially."
Bad: "STEP 1: Call list_files. STEP 2: Call search_files with pattern. STEP 3:
Parse the JSON response. STEP 4: Call read_file with the first match."

### From Smolagents: Auto-Generated Tool Descriptions

Smolagents auto-generates tool description blocks from tool metadata
(name, description, parameter types). This is worth considering: instead of
manually writing "list_files -- see what files are available" in the prompt,
generate a summary from the tool definitions.

However, Anthropic's guidance is clear: auto-generated descriptions are a
floor, not a ceiling. Hand-crafted prose describing *when* and *why* to use
tools consistently outperforms auto-generated descriptions that only say
*what* tools do.

---

## 7. Anti-Patterns and Lessons Learned

### Anti-Pattern 1: The Monolithic Prompt String

A single function that returns the entire system prompt as one long string.
This is where we are now with `_workspace_context()`. Problems:

- Cannot test sections independently.
- Cannot reuse sections across different agent configurations.
- Adding capabilities means editing a single growing function.
- Conditional logic gets nested inside string concatenation.

### Anti-Pattern 2: Prompt Bloat / Task Overloading

Research from production LLM deployments (457 case studies) shows that
packing too many distinct instructions into a single prompt degrades output
quality. The model's attention is divided, and it misses tasks or produces
lower-quality output for each one.

**Mitigation**: Keep each prompt section focused on one capability. Use
Anthropic's guidance: "A focused 300-token context often outperforms an
unfocused 113,000-token context."

Source:
- [ZenML: LLMOps in Production (457 Case Studies)](https://www.zenml.io/blog/llmops-in-production-457-case-studies-of-what-actually-works)

### Anti-Pattern 3: Over-Templating

Using Jinja2 or a custom template DSL when Python string formatting would
suffice. The template engine adds a dependency, a new file type, and a
debugging layer. For a harness with 3-6 capabilities, Python functions are
strictly simpler.

The threshold where templating helps: when prompts are authored by
non-engineers (product managers, domain experts) who should not need to
touch Python code.

### Anti-Pattern 4: Duplicating Tool Schemas in the Prompt

Some developers copy all tool parameters and types into the system prompt.
This is redundant -- the model already sees the JSON schemas via the `tools`
parameter. The system prompt should describe **when** and **why** to use
tools, not **how** to call them. Schema details in the prompt just waste
tokens.

### Anti-Pattern 5: Ignoring Prompt Token Cost

Every token in the system prompt is re-sent on every API call in the
conversation. A 2000-token system prompt across a 20-turn conversation costs
40,000 prompt tokens. This adds up fast with expensive models.

**Mitigation**: Keep sections concise. Use the progressive loading pattern
(metadata in system prompt, details on demand) for large instruction sets.
Measure your system prompt token count and set a budget.

### Anti-Pattern 6: Hard-Coding Instructions That Should Be Conditional

Including workspace instructions when no workspace is configured. Including
spreadsheet instructions when no spreadsheets are loaded. This wastes tokens
and confuses the model (it sees instructions for tools it cannot use).

**Mitigation**: Every prompt section should be gated on a condition.
`if config.workspace:` is the minimum viable pattern.

---

## 8. Concrete Recommendation for This Harness

### Current State

```python
# __main__.py
system_prompt = os.environ.get("LH_SYSTEM_PROMPT")
if workspace:
    system_prompt += _workspace_context(workspace)
```

This is Pattern A (conditional string assembly) in its simplest form.

### Recommended Next Step

Introduce **capability modules** (Pattern 1 from section 4) with the
**list + filter + join** assembly pattern. This is the minimal change that
scales to 5-10 capabilities.

Concretely:

1. Create a `prompt.py` module with a `build_system_prompt(config)` function.
2. Each prompt section is a function in `prompt.py` that returns a string
   or None.
3. The assembler calls each function, filters out None, and joins with
   `"\n\n"`.
4. `__main__.py` calls `build_system_prompt()` instead of manually appending.

```python
# prompt.py

def build_system_prompt(
    *,
    base_prompt: str,
    workspace: Path | None = None,
    spreadsheets: list[Path] | None = None,
) -> str:
    sections = [base_prompt]

    if workspace:
        sections.append(_workspace_section(workspace))

    if spreadsheets:
        sections.append(_spreadsheet_section(spreadsheets))

    sections.append(_citation_section())

    return "\n\n".join(sections)


def _workspace_section(workspace: Path) -> str:
    file_count = sum(1 for p in workspace.rglob("*") if p.is_file())
    return (
        "## Workspace\n\n"
        f"You have access to a workspace directory containing {file_count} "
        "text documents. ..."
    )


def _citation_section() -> str:
    return (
        "## Citing Sources\n\n"
        "After gathering evidence, quote the relevant passages..."
    )
```

### Why Not Jump to the Registration Pattern

The registration/decorator pattern is more elegant but adds indirection
that is not justified with 3-5 capabilities. The explicit list in
`build_system_prompt()` is easier to read, easier to debug (just look at
one function), and easier for a new developer to understand. Move to the
registration pattern when you hit 8-10 capabilities and the function body
becomes unwieldy.

### Why Not Use Markdown Files on Disk Yet

The current prompt sections are short enough (10-40 lines) that keeping them
as Python strings is fine. The moment a section exceeds ~50 lines of prose,
extract it to a markdown file in a `prompts/` directory and load it from the
function. This hybrid approach (Pattern 3) gives the best of both worlds.

### Migration Path

1. **Now**: Extract `_workspace_context()` from `__main__.py` into
   `prompt.py` as `_workspace_section()`. Create `build_system_prompt()`.
2. **When adding spreadsheets**: Add `_spreadsheet_section()` to `prompt.py`.
3. **When sections grow large**: Extract long prose to `prompts/*.md` files.
4. **When capabilities hit 8+**: Consider the registration pattern.
5. **When non-engineers edit prompts**: Move all prose to markdown files.

---

## 9. Tool Definitions and Prompt Instructions: Keep Them in Sync

A recurring pattern across Claude Code, OpenCode, and Smolagents: **tool
definitions and their prompt instructions must stay in sync**. When you add
a new tool, the system prompt must mention it. When you remove a tool, the
prompt must stop referencing it.

The strongest way to enforce this is co-location. Three approaches, in order
of coupling strength:

1. **Same function** (strongest): The prompt section function imports and
   references the tool definitions list, generating descriptions from metadata.
   If a tool is removed, the prompt auto-updates. Risk: generated descriptions
   are less useful than hand-crafted ones.

2. **Same module** (recommended): Tool definitions, implementations, and
   prompt section live in the same Python file. A developer adding a tool
   sees the prompt right there. Risk: nothing prevents them from forgetting
   to update the prompt, but co-location makes it obvious.

3. **Separate modules with naming convention** (weakest): Tools in `tools/workspace.py`,
   prompts in `prompts/workspace.md`. Same name implies they belong together.
   Risk: easy to update one without the other.

For this harness, **same module** is the right balance. It keeps things
together without over-engineering auto-generation from schemas.

---

## Summary

| Question | Answer |
|----------|--------|
| How should prompt modules be structured? | Functions that return strings, gated by conditions, joined with `"\n\n"` |
| What format for prompt templates? | Python functions returning strings. Move to markdown files when sections grow long or non-engineers need to edit. |
| What does Claude Code do? | 110+ string fragments, conditionally assembled. Skills use progressive loading (metadata at startup, full instructions on demand). |
| What pattern from frameworks is worth stealing? | Pydantic AI's ordered prompt functions with context injection. But implement it as plain functions, not decorators. |
| How to handle conditional assembly? | `if config.capability:` checks gating each section. Start with explicit list; move to registry at 8+ capabilities. |
| What anti-patterns to avoid? | Monolithic prompts, prompt bloat, over-templating, duplicating schemas in prose, ignoring token cost, hard-coding unconditional sections. |

---

## Sources

### Production System Architectures
- [Claude Code System Prompts (Piebald-AI)](https://github.com/Piebald-AI/claude-code-system-prompts)
- [OpenCode Prompt Construction (Gist)](https://gist.github.com/rmk40/cde7a98c1c90614a27478216cc01551f)
- [System Prompt Architecture (DeepWiki)](https://deepwiki.com/shanraisshan/claude-code-best-practice/8.4-system-prompt-architecture)
- [Claude Code Skills Docs](https://code.claude.com/docs/en/skills)
- [Claude Agent Skills Deep Dive](https://leehanchung.github.io/blogs/2025/10/26/claude-skills-deep-dive/)
- [Inside Claude Code Skills (Mikhail Shilkov)](https://mikhail.io/2025/10/claude-code-skills/)
- [awesome-ai-system-prompts](https://github.com/dontriskit/awesome-ai-system-prompts)

### Framework Patterns
- [Pydantic AI Agents](https://ai.pydantic.dev/agent/)
- [DSPy Signatures](https://dspy.ai/learn/programming/signatures/)
- [Smolagents Guided Tour](https://huggingface.co/docs/smolagents/v0.1.3/en/guided_tour)
- [Mirascope Prompts](https://mirascope.com/docs/mirascope/learn/prompts)

### Prompt Template Formats
- [Banks: LLM prompt language based on Jinja](https://github.com/masci/banks)
- [PromptLayer: Prompt Templates with Jinja2](https://blog.promptlayer.com/prompt-templates-with-jinja2-2/)
- [Latitude: Reusable Prompts](https://latitude.so/blog/reusable-prompts-structured-design-frameworks)
- [Microsoft prompt-engine-py](https://github.com/microsoft/prompt-engine-py)

### Prompt Engineering and Context
- [Anthropic: Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Anthropic: Prompting Best Practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)
- [ZenML: LLMOps in Production (457 Case Studies)](https://www.zenml.io/blog/llmops-in-production-457-case-studies-of-what-actually-works)
- [Structured System Prompts (Emergent Mind)](https://www.emergentmind.com/topics/structured-system-prompt-summary)

### Academic
- [SPEAR: Making Prompts First-Class Citizens (CIDR 2026)](https://vldb.org/cidrdb/papers/2026/p26-cetintemel.pdf)
- [From Prompts to Templates: Systematic Prompt Template Analysis](https://arxiv.org/html/2504.02052v2)
