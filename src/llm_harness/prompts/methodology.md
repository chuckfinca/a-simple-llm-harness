## Methodology

Write Python code using the workspace functions. Combine multiple operations into a single code block to minimize tool calls.

```python
from tools import list_files, search_files, read_file
import json

# Do multiple things in one step: search, then read the top results
results = json.loads(search_files("faction|factions"))
for match in results["matches"][:3]:
    content = json.loads(read_file(match["file"]))
    print(f"=== {match['file']} (line {match['line']}) ===")
    print(content["content"][:2000])
```

All functions return JSON strings — use `json.loads()` to parse them. Call `help()` to see full signatures.

Key points:
- **Batch operations.** Search and read in the same code block. Never make a separate call just to list or search — combine it with the read that follows.
- **Use function parameters.** `read_file(path, offset=100, limit=50)` reads 50 lines starting at line 100. `search_files("judge|judicial|judiciary")` searches variants in one call. Don't paginate by slicing strings.
- **Stop early.** 2-4 productive tool calls should suffice for most questions. If you have the passages you need, answer immediately.