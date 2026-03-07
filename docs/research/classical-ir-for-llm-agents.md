# Classical IR Techniques as Teachable Heuristics for LLM Agents

Date: 2026-03-06

## Purpose

This document distills classical information retrieval (IR) research into
actionable heuristics that can be taught to an LLM agent through system prompt
instructions. The agent has regex-based search tools (`search_files`,
`list_files`, `read_file`) over ~85 text documents. The goal is not to build a
search engine but to make the agent a better searcher by encoding expert search
behavior as natural language instructions.

Companion document: `search-strategy-planning.md` covers agentic patterns
(ReAct, plan-and-execute, ReWOO) and practical implementation. This document
covers the IR foundations that inform *what* those patterns should do.

---

## 1. Keyword Selection: Choosing Effective Search Terms

### The IDF Intuition

Karen Sparck Jones (1972) established the foundational insight behind inverse
document frequency (IDF): **a term that appears in many documents is a poor
discriminator; a term that appears in few documents is a strong discriminator.**

The practical implication for an LLM agent: when choosing which words from a
question to search for, prefer the words that are most likely to appear *only*
in relevant documents and not everywhere else.

Salton and Buckley (1988) confirmed experimentally that single-term retrieval
with good term weighting outperforms more elaborate text representations. The
quality of the search terms matters more than the sophistication of the search
mechanism.

### Teachable Heuristics for Term Selection

**Prefer nouns over verbs and function words.** Nouns carry topical specificity.
The question "Which papers discuss the judiciary?" contains one high-value
search term ("judiciary") and several low-value ones ("which", "papers",
"discuss"). An agent should extract the content-bearing nouns and ignore the
rest.

**Prefer specific terms over general ones.** "Spinning jenny" is a better
search term than "invention." "Habeas corpus" is better than "legal concept."
The more specific a term, the fewer irrelevant documents it matches, and the
higher the proportion of results that are actually relevant. This is the IDF
principle stated as a search heuristic.

**Prefer rare or distinctive terms.** If a user asks about "environmental
impact assessments for coastal wetland development," the agent should
prioritize "wetland" and "coastal" over "environmental" and "development."
The latter appear in many contexts; the former are topic-specific.

**Use domain-specific vocabulary when available.** Technical terms, proper
nouns, and jargon are almost always better search terms than their plain-
language equivalents. "Amortization" retrieves more precisely than "paying
off a loan over time."

**Drop terms that describe the task rather than the topic.** Words like
"discuss," "analyze," "describe," "compare," and "explain" describe what
the user wants the agent to do, not what the documents contain. These should
never be search terms.

### The BM25 Intuition

Robertson's BM25 (Okapi BM25) adds two refinements to tf-idf that translate
into useful agent heuristics:

**Term frequency saturation.** The first few occurrences of a term in a
document are highly indicative of relevance. After a point, additional
occurrences add diminishing signal. For an agent: if a document mentions your
search term many times, it is probably relevant -- but a document mentioning
it 50 times is not necessarily more relevant than one mentioning it 10 times.
Do not over-weight high-frequency matches.

**Document length normalization.** A short document that contains your search
term is a stronger signal than a long document that contains it. A 200-word
document about "judicial review" that mentions the term 3 times is more
topically focused than a 10,000-word document that mentions it 3 times
incidentally. For an agent: when multiple documents match, shorter documents
with concentrated matches deserve more attention.

---

## 2. Query Expansion: Learning from Results

### Rocchio Relevance Feedback

The Rocchio algorithm (1971, from the SMART system at Cornell) formalizes a
simple idea: **move your query toward the terms found in relevant documents
and away from the terms found in irrelevant ones.**

The mathematical formulation is not important for an LLM agent. The behavioral
principle is:

1. Run an initial search
2. Look at the results
3. Identify terms that appear in the relevant results but were not in your
   original query
4. Add those terms to your next search
5. Identify terms that appear in irrelevant results and avoid those

This is the formal basis for the "search, evaluate, refine" loop.

### Pseudo-Relevance Feedback

Pseudo-relevance feedback automates the Rocchio process by assuming the top-K
results from an initial search are relevant (without human judgment). The
system extracts terms from those top results and adds them to a refined query.

**Typical parameters from the literature:**
- Assume the top 5-10 documents are relevant
- Extract 20-30 new candidate terms from those documents
- The best expansion terms are those that appear frequently in the top
  results but infrequently in the collection overall (high tf in relevant
  docs, high idf across the collection)

**For an LLM agent, the simplified version is:**
1. Search for your initial terms
2. Read the top 2-3 matching documents (or their titles/first lines)
3. Notice what vocabulary those documents use
4. Search for any new relevant terms you discover

### When Expansion Helps vs. Hurts

Expansion works well when:
- The initial query uses non-standard terminology (the user says "car crash"
  but the documents say "motor vehicle accident")
- The topic has multiple valid names (the user says "global warming" but some
  documents say "climate change")
- The initial query is short and underspecified

Expansion hurts when:
- The initial query is already precise and well-matched to the corpus
  vocabulary
- Added terms introduce ambiguity (expanding "java" might pull in documents
  about both the programming language and the island)
- Too many expansion terms dilute the query's focus, drowning relevant
  results in noise

**Teachable heuristic:** Expand aggressively when the first search returns
few results. Expand cautiously (or not at all) when the first search returns
many relevant results. Never expand with ambiguous terms without narrowing
context.

---

## 3. Boolean Search Strategy: AND, OR, and Term Combination

### Core Boolean Logic for Agents

**OR broadens.** Searching for "court OR tribunal OR judiciary" retrieves
documents containing any of these terms. Use OR when you want to capture a
concept that may be expressed with different words (synonyms, alternate
spellings, related terms).

**AND narrows.** Searching for "court AND reform" retrieves only documents
containing both terms. Use AND when your topic sits at the intersection of
two concepts.

**NOT excludes.** Searching for "mercury NOT planet" excludes documents about
the planet. Use NOT sparingly -- it can remove documents that discuss both
topics, which may actually be relevant.

### When to Search Terms Together vs. Separately

This is one of the most important decisions an agent makes, and the IR
literature is clear:

**Search synonyms separately (with OR logic).** If you are looking for
documents about courts and your terms are "court," "tribunal," and
"judiciary," searching for all three at once with AND would require a document
to contain all three words -- almost certainly returning nothing. These are
alternative expressions of the same concept and should be searched with OR
(or as separate searches whose results are combined).

**Search cross-concept terms together (with AND logic).** If you want
documents about judicial reform specifically, searching "judicial" and
"reform" together is appropriate because these represent two distinct facets
of the information need that must co-occur.

**Teachable heuristic for agents:** Ask yourself: "Are these terms different
ways of saying the same thing (synonyms), or different things that must both
be present?" Synonyms get separate searches. Distinct facets get combined
searches.

### Practical Strategy for Regex Tools

Since our agent uses regex `search_files` rather than a boolean query
language, the agent must implement boolean logic through its search behavior:

- **OR**: Run separate searches for each synonym, combine results
- **AND**: Search for one term, then check which of those results also
  contain the second term (by reading the files)
- **NOT**: Filter results mentally after reading, excluding documents that
  are off-topic despite matching the search term

---

## 4. Recall vs. Precision: When to Cast Wide vs. Narrow

### The Fundamental Tradeoff

Buckland and Gey (1994) established that the tradeoff between recall and
precision is unavoidable: retrieving more documents increases the chance of
finding all relevant ones (higher recall) but also increases the number of
irrelevant ones (lower precision). Retrieving fewer documents increases the
proportion that are relevant (higher precision) but risks missing some
(lower recall).

### Matching Strategy to Task

The right balance depends on what the user needs:

**High-recall tasks** (cast a wide net):
- "Find ALL documents that mention X"
- "Are there any documents about X?" (existence check)
- Comprehensive surveys or literature reviews
- Questions where missing a document would be worse than reading extras

**High-precision tasks** (narrow search):
- "What does the corpus say about X?" (need a few good sources)
- "Find the document that defines X" (looking for one specific thing)
- Questions where reading irrelevant documents wastes time

**Teachable heuristic:** If the user asks for "all" or "every" or "any,"
prioritize recall -- search broadly with many terms and accept noise. If
the user asks for "the" or "which" or wants a specific answer, prioritize
precision -- search narrowly and verify results.

### Knowing When You Have Enough

There is no formula for knowing when recall is complete, but these heuristics
help:

**Diminishing returns signal.** If your last 2-3 searches returned no new
relevant documents, you have probably found most of what exists. Each
additional search has decreasing marginal value.

**Coverage check.** After searching, ask: "Have I searched for all the major
synonyms and related terms for this concept?" If you can think of more terms
you have not tried, you are not done.

**Cross-reference check.** If relevant documents reference other documents
(by name or topic), check whether those referenced documents are in your
result set. Missing cross-references suggest gaps in coverage.

**Proportionality check.** In a corpus of 85 documents, finding 20+ documents
on a narrow topic would be surprising. Finding only 1 document on a broad
topic should trigger more searching.

---

## 5. Search Iteration: The Berrypicking Model

### Bates' Berrypicking (1989)

Marcia Bates' berrypicking model overturned the assumption that search is a
single query-to-results transaction. Her two key observations:

1. **The information need changes as you search.** Each document you find
   teaches you something that shifts what you are looking for. A search for
   "judicial reform" might lead you to discover that "sentencing guidelines"
   is a relevant sub-topic you had not considered.

2. **Satisfaction comes from accumulation, not a single result set.** The
   answer is assembled from bits found across multiple searches, not from
   one perfect query.

This directly maps to how an LLM agent should behave: search is iterative,
and each result informs the next search. An agent that treats search as a
single lookup is using the wrong mental model.

### Bates' 29 Search Tactics (1979)

Bates identified 29 specific tactics across four categories. The most
relevant for an LLM agent:

**Monitoring Tactics (staying on track):**
- **CHECK**: Periodically compare your current search direction against the
  original question. It is easy to drift.
- **RECORD**: Keep track of which searches you have already run so you do
  not repeat them and can identify gaps.
- **WEIGH**: Consider whether the next search is worth the cost. If you
  already have strong results, another search may not add value.

**Search Formulation Tactics (structuring queries):**
- **SPECIFY**: Start with specific terms. You can always broaden later, but
  starting broad produces noise.
- **EXHAUST**: Include all the key facets of the question in your initial
  search plan.
- **REDUCE**: If a multi-term search returns nothing, drop the least
  important term and try again.
- **PARALLEL**: For each concept, generate parallel terms (synonyms) and
  search for each.
- **BLOCK**: Exclude terms that consistently produce irrelevant results.

**Term Tactics (choosing and revising terms):**
- **SUPER**: Broaden by moving to a more general term ("court" -> "legal
  system").
- **SUB**: Narrow by moving to a more specific term ("legal system" ->
  "appellate court").
- **RELATE**: Try coordinate terms at the same level of specificity
  ("court" -> "tribunal").
- **TRACE**: When you find a relevant document, mine it for new search
  terms. What vocabulary does it use?
- **CONTRARY**: If searching for a concept yields nothing, try searching
  for its opposite (searching for arguments "against" something may find
  documents that discuss both sides).

### The Iterative Refinement Pattern

Synthesizing Bates, Rocchio, and modern search research, the proven search
iteration pattern is:

```
1. PLAN: Analyze the question. Identify key concepts and generate multiple
   search terms for each concept (synonyms, related terms, specific/general
   variants).

2. SEARCH: Execute searches for the most promising terms first. Start with
   specific terms before general ones.

3. EVALUATE: Look at what you found. Are the results relevant? Are there
   obvious gaps? Did the results reveal new terminology?

4. REFINE: Based on evaluation:
   - If too few results: broaden terms (SUPER), add synonyms (PARALLEL),
     drop restrictive terms (REDUCE)
   - If too many irrelevant results: narrow terms (SUB), add restricting
     terms (AND), exclude noise (BLOCK)
   - If results suggest new directions: extract new terms (TRACE) and
     search for them

5. STOP when: diminishing returns (last searches found nothing new),
   coverage feels complete (all major synonyms tried), or the question
   is answered.
```

---

## 6. Document Structure: Where to Look First

### Zone Weighting

Manning, Raghavan, and Schutze (2008) formalize what librarians know
intuitively: **not all parts of a document are equally indicative of its
topic.** In zone-weighted scoring, matches in certain document zones receive
higher weight.

The typical hierarchy of informativeness:
1. **Title/filename** -- highest signal. A document titled "Judicial Reform
   Proposals" is almost certainly about judicial reform, regardless of what
   the body says.
2. **Headings/subheadings** -- strong signal. Section headers summarize what
   each section covers.
3. **First paragraph/introduction** -- strong signal. Most well-written
   documents state their topic upfront.
4. **Concluding paragraph** -- moderate signal. Summaries restate key points.
5. **Body text** -- moderate signal. Relevant terms may appear in passing
   without the document being "about" the topic.
6. **Footnotes/references** -- weak signal. A passing citation does not mean
   the document is about the cited topic.

### Teachable Heuristics for Agents

**Check filenames first.** `list_files` is cheap. A filename like
`judicial-reform.txt` tells you more than any content search. Always scan
filenames before or alongside content searches.

**Skim before reading.** When evaluating whether a document is relevant, read
the first few lines before reading the whole thing. If the opening paragraph
is clearly off-topic, move on. This is the agent equivalent of scanning
a table of contents.

**Weight title matches heavily.** If your search term appears in a document's
title or filename, that document is almost certainly relevant. If it appears
only deep in the body text, it may be a passing mention.

**Use document structure for term discovery.** Headings and subheadings in
relevant documents often contain terms you should be searching for. If you
find a relevant document with a section called "Sentencing Guidelines,"
that is a signal to search for "sentencing guidelines" as well.

---

## 7. Additional Teachable Heuristics from IR and Library Science

### Pearl Growing (Pennant Growing, Citation Chasing)

Start with one known-relevant document and use it to find more:
1. Find one document you know is relevant
2. Extract its key terms, especially terms you had not thought of
3. Search for those new terms
4. Repeat with each new relevant document found

This is the searcher's equivalent of following footnotes in academic research.
The technique was formalized in library science and has been shown to be more
comprehensive than database searching alone for identifying all relevant
material.

### The Vocabulary Problem

Furnas et al. (1987) demonstrated that people use remarkably diverse
vocabulary to describe the same concept. In their study, the probability
that two people would use the same term to describe something was less than
20%. This means a single-keyword search inherently misses most relevant
documents.

**The implication is stark:** any search strategy that uses only one term per
concept will fail most of the time. Multiple terms are not optional -- they
are necessary.

### Exhaustive vs. Quick Search Modes

Expert searchers (as studied by Hsieh-Yee, 1993, and others) switch between
two modes:

**Quick mode:** Issue a short, imprecise query to get into the right
neighborhood, then navigate from there. Used when the information need is
simple or when time is limited.

**Exhaustive mode:** Systematically search all synonyms, related terms, and
variant phrasings. Used when completeness matters.

The agent should match its mode to the question:
- "What is X?" -> Quick mode. Find one good source and answer.
- "Which documents discuss X?" -> Exhaustive mode. Search systematically
  for all variants.

### Expert vs. Novice Searcher Differences

Research consistently finds that expert searchers differ from novices in
specific, teachable ways:

- **Experts plan before searching.** They spend time thinking about search
  terms before issuing the first query. Novices start searching immediately.
- **Experts use more specific terms.** Novices tend to use broad, general
  terms that return too many results.
- **Experts iterate and adapt.** When results are poor, experts change their
  strategy (different terms, different approach). Novices repeat the same
  search or give up.
- **Experts monitor their progress.** They track what they have searched for
  and evaluate whether the results are sufficient. Novices lack this
  metacognitive layer.
- **Experts know when to stop.** They recognize diminishing returns and do
  not over-search. Novices either stop too early (after one search) or
  search indefinitely without evaluating.

### Query Decomposition for Multi-Faceted Questions

Complex questions should be broken into independently searchable sub-
questions. "Which documents discuss the economic impact of judicial reform?"
has two facets:
1. Documents about judicial reform
2. Documents about economic impact

Search each facet independently, then find the intersection. This prevents
the failure mode where a combined search ("economic judicial reform") is too
specific and returns nothing, while individual searches for each facet
identify the relevant documents.

### The Specificity-First Heuristic

Start with your most specific, most distinctive terms. If they work, you are
done. If they return nothing, systematically broaden:

```
Level 1: "habeas corpus" (exact phrase, highly specific)
Level 2: "habeas" (single distinctive term)
Level 3: "detention" OR "imprisonment" (related concepts)
Level 4: "legal rights" (general category)
```

Each level trades precision for recall. An agent should start at Level 1 and
move down only when higher levels fail. This is Bates' SPECIFY tactic
combined with REDUCE as a fallback.

### Morphological Awareness

The same concept appears in different morphological forms:
- "judge" / "judges" / "judging" / "judicial" / "judiciary"
- "reform" / "reforms" / "reforming" / "reformed" / "reformation"
- "regulate" / "regulation" / "regulatory" / "regulator"

Since our agent cannot rely on stemming (the search tool does exact regex
matching), it must explicitly search for morphological variants. The agent
should consider: singular/plural, verb/noun/adjective forms, and common
derivational forms.

For regex-capable tools, this can sometimes be handled with patterns like
`judg(e|es|ing|ment)` or `reform(s|ing|ed|ation)?`, but the agent should
know that generating separate searches for key variants is also valid.

---

## 8. Summary: A Teaching Checklist for the Agent

These are the core behaviors from classical IR that an LLM agent should
follow when searching a text corpus. Each is expressed as an instruction
that could appear in a system prompt:

### Before Searching
1. Extract the content-bearing nouns from the question. Ignore task words
   like "discuss," "analyze," and "describe."
2. For each key concept, generate synonyms, related terms, and morphological
   variants. A single term will miss most relevant documents.
3. Identify the most specific and distinctive terms -- these should be
   searched first.
4. Decide whether this is a quick-answer task (find one good source) or an
   exhaustive-search task (find all relevant documents). Match your effort
   to the task.
5. If the question has multiple facets, plan to search each facet
   independently.

### During Searching
6. Check filenames first. Titles are the strongest signal of document
   relevance.
7. Start with specific terms, then broaden only if needed.
8. Search synonyms separately and combine the results. Do not AND synonyms
   together.
9. When combining distinct concepts, check that results contain both
   concepts (AND logic).
10. After each search, skim results before deep reading. Read the first few
    lines of promising documents to verify relevance.
11. When you find a relevant document, mine it for new search terms (pearl
    growing). Note vocabulary the document uses that you have not searched
    for.

### After Each Search Round
12. Evaluate: Did this search return relevant results? Are there obvious
    gaps?
13. If too few results: broaden terms, try synonyms, drop restrictive terms.
14. If too many irrelevant results: use more specific terms, add qualifying
    terms, exclude noisy terms.
15. If results suggest new vocabulary: search for the new terms.

### When to Stop
16. Your last 2-3 searches returned no new relevant documents (diminishing
    returns).
17. You have searched all major synonyms and related terms for each key
    concept.
18. The number of results is proportionate to what you would expect for this
    topic in a corpus of this size.
19. The question is answered.

---

## Sources

### Foundational IR Research
- Sparck Jones, K. (1972). "A statistical interpretation of term specificity
  and its application in retrieval." *Journal of Documentation*, 28(1).
  Established the IDF concept.
- Salton, G. & Buckley, C. (1988). "Term-weighting approaches in automatic
  text retrieval." *Information Processing & Management*, 24(5).
  [Semantic Scholar](https://www.semanticscholar.org/paper/Term-Weighting-Approaches-in-Automatic-Text-Salton-Buckley/e50a316f97c9a405aa000d883a633bd5707f1a34)
- Robertson, S.E. & Sparck Jones, K. (1976). "Relevance weighting of search
  terms." *Journal of the American Society for Information Science*, 27(3).
  [Wiley](https://asistdl.onlinelibrary.wiley.com/doi/abs/10.1002/asi.4630270302)
- Robertson, S.E. et al. BM25 / Okapi weighting.
  [Wikipedia](https://en.wikipedia.org/wiki/Okapi_BM25)
- Fang, H. et al. "A Formal Study of Information Retrieval Heuristics."
  [PDF](https://www.eecis.udel.edu/~hfang/pubs/sigir04-formal.pdf)
- Furnas, G.W. et al. (1987). "The vocabulary problem in human-system
  communication." *Communications of the ACM*.
- Robertson, S.E. "Understanding Inverse Document Frequency."
  [PDF](https://www.staff.city.ac.uk/~sbrp622/idfpapers/Robertson_idf_JDoc.pdf)

### Search Behavior and Tactics
- Bates, M.J. (1979). "Information Search Tactics." *Journal of the American
  Society for Information Science*, 30(4).
  [Full text](https://pages.gseis.ucla.edu/faculty/bates/articles/Information%20Search%20Tactics.html)
- Bates, M.J. (1989). "The Design of Browsing and Berrypicking Techniques."
  [Full text](https://pages.gseis.ucla.edu/faculty/bates/berrypicking.html)
- Hearst, M. (2009). *Search User Interfaces*. Cambridge University Press.
  [Chapter 3](https://searchuserinterfaces.com/book/sui_ch3_models_of_information_seeking.html)
- Huang, J. & Efthimiadis, E. (2009). "Analyzing and Evaluating Query
  Reformulation Strategies in Web Search Logs." *CIKM*.
  [PDF](https://jeffhuang.com/papers/Reformulation_CIKM09.pdf)

### Query Expansion and Relevance Feedback
- Rocchio, J.J. (1971). "Relevance Feedback in Information Retrieval."
  From the SMART system, Cornell.
  [Wikipedia](https://en.wikipedia.org/wiki/Rocchio_algorithm)
- Manning, C.D., Raghavan, P. & Schutze, H. (2008). *Introduction to
  Information Retrieval*. Cambridge University Press.
  [Chapter 9: Query Expansion](https://nlp.stanford.edu/IR-book/pdf/09expand.pdf)
  [Full book online](https://nlp.stanford.edu/IR-book/information-retrieval-book.html)
- [Relevance Feedback overview](https://en.wikipedia.org/wiki/Relevance_feedback)

### Recall and Precision
- Buckland, M. & Gey, F. (1994). "The Relationship between Recall and
  Precision." *Journal of the American Society for Information Science*.
  [PDF](https://escholarship.org/content/qt0g80268t/qt0g80268t_noSplash_aaf9300d2ff022ba6d96f424debf50f0.pdf)
- [Precision and Recall](https://en.wikipedia.org/wiki/Precision_and_recall)

### Boolean Search
- [Combining Terms with Boolean Operators (U. of Illinois)](https://guides.library.illinois.edu/c.php?g=1191165&p=8712534)
- [Boolean Operators (MIT Libraries)](https://libguides.mit.edu/c.php?g=175963&p=1158594)

### Pearl Growing and Citation Chasing
- [Pearl Growing (Wikipedia)](https://en.wikipedia.org/wiki/Pearl_growing)
- [Pearling and Footnote Chasing](https://blogs.uoregon.edu/annie/2016/02/07/pearling-and-footnote-chasing/)

### Expert vs. Novice Search Behavior
- [How Experts and Novices Search the Web (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S0740818805000095)
- [Models of the Information Seeking Process (Hearst)](https://searchuserinterfaces.com/book/sui_ch3_models_of_information_seeking.html)

### LLM Agent Search and Agentic RAG
- [Agentic RAG Survey (arXiv 2501.09136)](https://arxiv.org/abs/2501.09136)
- [Narrowing or Broadening Search Results (UNR Library)](https://library.unr.edu/help/quick-how-tos/searching/search-tips/narrowing-or-broadening-search-results)
