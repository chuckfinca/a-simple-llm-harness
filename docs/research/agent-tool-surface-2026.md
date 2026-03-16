# Agent Tool Surface: Industry Catalog (2026)

**Date:** 2026-03-15
**Source:** Trends scout research agent

## Summary

Catalog of what tools major agent systems ship with, the converging standard,
and implications for our harness. The industry has converged on a small core
tool set with code execution as the universal data/computation tool.

## Tool Catalogs by System

### Claude Code (18+ built-in tools)
- **Filesystem**: Read, Edit, MultiEdit, Write, Glob, Grep, LS, NotebookEdit
- **Execution**: Bash (persistent shell session with timeout)
- **Web**: WebSearch, WebFetch
- **Planning**: TodoRead, TodoWrite, EnterPlanMode, ExitPlanMode
- **Coordination**: Agent (sub-agents), SendMessage, Skill
- **Other**: AskUserQuestion, LSP, CronCreate, Computer (browser automation)

### OpenAI Codex CLI
- **Filesystem**: read_file, list_dir, glob_file_search, apply_patch
- **Search**: rg (ripgrep)
- **Execution**: shell commands (with approval controls)
- **Planning**: todo_write, update_plan
- **Web**: web_search (optional, off by default)
- **Extensibility**: MCP server integration

### OpenAI Responses API / Agents SDK
- **Web**: WebSearchTool
- **Retrieval**: FileSearchTool (vector store RAG)
- **Execution**: CodeInterpreterTool (sandboxed Python)
- **Computer**: Computer use (GUI automation)
- **Extensibility**: MCP support, custom function tools

### SWE-Agent
- **Filesystem**: open, create, edit (line-range replacement)
- **Navigation**: goto, scroll_up, scroll_down
- **Search**: search_dir, search_file, find_file
- **Execution**: bash
- **Note**: mini-swe-agent reduces to JUST bash and achieves 74%+ on SWE-bench

### smolagents (HuggingFace)
- **Search**: DuckDuckGoSearchTool, GoogleSearchTool, WikipediaSearchTool
- **Web**: VisitWebpageTool
- **Execution**: PythonInterpreterTool
- **Interaction**: UserInputTool, FinalAnswerTool
- **Note**: No built-in filesystem tools — designed as web-first research agent

### Google ADK
- **Search**: google_search
- **Execution**: BuiltInCodeExecutor (sandboxed Python)
- **Retrieval**: RAG/Vertex AI Search
- **Extensibility**: MCP, LangChain tools, LlamaIndex tools

## The Converging Standard

### Universal (every system has these)
1. **Read file/document** — access to input material
2. **Search content** — navigate large inputs (grep/ripgrep)
3. **Execute code** — computation, data analysis, format conversion
4. **Web search** — access current information (except sandboxed coding agents)

### Near-universal (most systems)
5. **File discovery** — list/glob files
6. **Web fetch** — read specific URLs
7. **Write/edit files** — produce persistent output
8. **Task/plan tracking** — multi-step workflow state

### Common but not universal
9. Sub-agent spawning
10. Browser/computer use
11. RAG/vector search
12. Notebook editing
13. Version control (usually via bash)

## Tool Categories (Industry Taxonomy)

1. **Filesystem** — read, write, edit, list, glob, search content
2. **Execution** — bash/shell, Python interpreter, sandboxed code
3. **Search/Discovery** — web search, content search (grep), file discovery
4. **Web/Network** — fetch URL, browse, API calls
5. **Planning/Coordination** — todo lists, task tracking, sub-agent delegation
6. **Retrieval/Knowledge** — RAG, vector search, Wikipedia
7. **Version Control** — git (usually via shell)
8. **Communication** — user input, agent-to-agent messaging
9. **Media** — image generation, speech-to-text, computer use
10. **Data/Analysis** — code interpreter (pandas), spreadsheet operations

## Spreadsheet/Data Tools

**Industry consensus: don't build bespoke spreadsheet tools.**
Give the agent a Python interpreter with pandas/openpyxl and let it write code.

- OpenAI Code Interpreter: pandas via sandboxed Python
- LangChain: create_pandas_dataframe_agent (wraps Python execution)
- Google ADK: Code Executor with data libraries
- PandasAI: Conversational queries against DataFrames

**Exception**: LlamaIndex Spreadsheet Agent uses purpose-built arithmetic and
aggregation tools, arguing code execution is unreliable for complex spreadsheet
ops. Still in private preview.

## Tools Deliberately NOT Given to Agents

From Anthropic's tool design guidance and security research:

- **Network access in sandboxed environments** — prevents data exfiltration
- **Destructive operations without approval** — tiered approval modes
- **Too many overlapping tools** — "If a human can't say which tool to use,
  the AI can't either" (Anthropic)
- **Low-signal data tools** — return lightweight references, not full objects
- **One-tool-per-API-endpoint** — consolidate related operations

## Minimal Viable Tool Set

**Tier 1 — Absolute minimum (4 tools):**
1. Read file/document
2. Search/find content
3. Execute code
4. Provide answer

**Tier 2 — Standard productive agent (add 3-4):**
5. Write/edit files
6. Web search
7. Web fetch
8. List/discover files

**Tier 3 — Full-featured (add based on need):**
9. Task/plan tracking
10. Sub-agent delegation
11. RAG/vector retrieval
12. Browser/computer use

## Implications for Our Harness

| Our tool | Industry equivalent | Assessment |
|----------|-------------------|------------|
| list_files | Glob/LS | Standard |
| search_files | Grep | Standard |
| read_file | Read | Standard |
| run_python | PythonInterpreter / Bash | Standard |
| calculator | Usually subsumed by code execution | **Redundant** |
| get_current_time | Usually via code execution | **Redundant** |

**Key observations:**
- `calculator` + `run_python` is exactly the tool overlap Anthropic warns against
- `get_current_time` is trivially available via Python's datetime module
- Missing: web search, web fetch (near-universal in research agents)
- Missing: file write/edit (limits agent to read-only analysis)
- For spreadsheets: make pandas/openpyxl available in the sandbox, don't build
  dedicated spreadsheet tools

## Sources

- Claude Code tools: https://github.com/Piebald-AI/claude-code-system-prompts
- OpenAI Codex CLI: https://developers.openai.com/codex/cli/features/
- OpenAI Agents SDK: https://openai.com/index/new-tools-for-building-agents/
- smolagents: https://huggingface.co/docs/smolagents/main/reference/default_tools
- Google ADK: https://google.github.io/adk-docs/tools/built-in-tools/
- SWE-agent tools: https://swe-agent.com/latest/config/tools/
- Anthropic writing tools: https://www.anthropic.com/engineering/writing-tools-for-agents
- LlamaIndex Spreadsheet Agent: https://www.llamaindex.ai/blog/introducing-the-spreadsheet-agent-in-private-preview
- mini-swe-agent: https://github.com/SWE-agent/mini-swe-agent
