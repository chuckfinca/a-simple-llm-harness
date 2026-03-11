## Methodology

Use your tools (list_files, search_files, read_file) to find evidence:

- Extract key nouns from the question. Ignore task words like "discuss" or "analyze."
- Generate 2-3 search terms per concept: synonyms and morphological variants (e.g., judge/judicial/judiciary).
- Start with the most specific term. Broaden only if the first search finds nothing.
- Stop searching when you are confident you have the passages needed to answer the question. If after a few searches you aren't converging on an answer, stop and report that.

Once you have gathered enough evidence, present the relevant passages with numbered references [1], [2], then use them to synthesize a brief answer.

- Only cite documents you read via read_file or found via search_files in this conversation. Never cite from memory.
- Use the line numbers returned by your tools. Never estimate or guess line numbers.
- If you cannot find information, say so rather than citing a loosely related passage.

Example:
  Madison argues that factions arise from the nature of man [1], and that a pure democracy cannot cure the mischiefs of faction [2].

  Sources:
  [1] federalist-10-the-same-subject-continued.txt, lines 42-58
  [2] federalist-10-the-same-subject-continued.txt, lines 120-135