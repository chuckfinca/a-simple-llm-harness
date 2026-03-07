# Test Workspace Corpora for Retrieval Evaluation

We need 2-3 additional text corpora beyond the Federalist Papers to
stress-test different retrieval patterns in our LLM agent. The Federalist
Papers are uniform in style (18th-century political philosophy, single genre,
similar document lengths). The corpora below are chosen to expose weaknesses
that homogeneous political prose will not.

## Current Baseline: Federalist Papers

- 85 text files, 1.3 MB total
- Uniform genre, era, and vocabulary
- Tests: keyword search across related documents, author attribution,
  thematic synthesis
- Weakness as sole test set: does not test technical vocabulary, factual
  precision, cross-domain filtering, or "I don't know" responses

---

## Recommendation 1: Darwin's "On the Origin of Species"

**What it tests: Technical/scientific vocabulary and within-document navigation**

### Why This Corpus

Darwin's Origin of Species is dense scientific prose with precise terminology
(natural selection, sexual selection, hybridism, rudimentary organs,
geological succession). It forces the agent to handle:

- **Precise technical search terms** where synonyms fail (searching for
  "hybridism" vs. "crossbreeding" vs. "interbreeding" -- Darwin uses all
  three with different meanings)
- **Within-chapter navigation** -- chapters are long (40-70KB each), so the
  agent must search within files, not just find the right file
- **Hierarchical structure** -- unlike the flat Federalist Papers, Origin has
  chapters with internal sections, requiring the agent to understand document
  structure
- **Argumentation chains** -- Darwin builds arguments across chapters,
  testing whether the agent can trace reasoning across files

### Source and Download

- **Source:** Project Gutenberg, eBook #1228
- **URL:** https://www.gutenberg.org/ebooks/1228
- **Plain text:** https://www.gutenberg.org/files/1228/1228-0.txt
- **Raw size:** 949 KB (single file)
- **License:** Public domain

### Workspace Structure

Split the single file into 16 text files:

```
test-data/origin-of-species/
  00-introduction.txt
  01-variation-under-domestication.txt
  02-variation-under-nature.txt
  03-struggle-for-existence.txt
  04-natural-selection.txt
  05-laws-of-variation.txt
  06-difficulties-on-theory.txt
  07-instinct.txt
  08-hybridism.txt
  09-imperfection-of-the-geological-record.txt
  10-geological-succession-of-organic-beings.txt
  11-geographical-distribution.txt
  12-geographical-distribution-continued.txt
  13-mutual-affinities-morphology-embryology.txt
  14-recapitulation-and-conclusion.txt
  glossary-and-index.txt
```

### Splitting Script

```python
"""Split Origin of Species into chapter files."""
import re
import urllib.request
from pathlib import Path

url = "https://www.gutenberg.org/files/1228/1228-0.txt"
text = urllib.request.urlopen(url).read().decode("utf-8")

# Strip Gutenberg header/footer
start = text.index("INTRODUCTION.")
end = text.index("*** END OF THE PROJECT GUTENBERG EBOOK")
text = text[start:end].strip()

# Split on chapter markers
parts = re.split(r'\n(?=CHAPTER \d+\.)', text)

output_dir = Path("test-data/origin-of-species")
output_dir.mkdir(parents=True, exist_ok=True)

slug_map = {
    0: "00-introduction",
    1: "01-variation-under-domestication",
    2: "02-variation-under-nature",
    3: "03-struggle-for-existence",
    4: "04-natural-selection",
    5: "05-laws-of-variation",
    6: "06-difficulties-on-theory",
    7: "07-instinct",
    8: "08-hybridism",
    9: "09-imperfection-of-the-geological-record",
    10: "10-geological-succession-of-organic-beings",
    11: "11-geographical-distribution",
    12: "12-geographical-distribution-continued",
    13: "13-mutual-affinities-morphology-embryology",
    14: "14-recapitulation-and-conclusion",
}

for i, part in enumerate(parts):
    if i in slug_map:
        filename = slug_map[i] + ".txt"
        (output_dir / filename).write_text(part.strip())
        print(f"Wrote {filename} ({len(part)} bytes)")

# Handle glossary/index if present after chapter 14
```

### Evaluation Questions

1. **"What does Darwin mean by 'natural selection' and how does he
   distinguish it from artificial selection?"**
   - Tests: cross-chapter synthesis (chapters 1 and 4), precise terminology
   - Expected: agent searches both chapters, cites specific passages

2. **"What evidence does Darwin present from the fossil record, and what
   does he admit is missing?"**
   - Tests: navigating chapter 9 (Imperfection of the Geological Record),
     honest acknowledgment of gaps in Darwin's own argument
   - Expected: agent finds Darwin's candid admissions about missing
     transitional forms

3. **"How does Darwin explain the existence of complex organs like the eye?"**
   - Tests: searching within chapter 6 (Difficulties on Theory), finding the
     famous "eye" passage without an obvious keyword match to the chapter title
   - Expected: agent must search file contents, not rely on filenames

4. **"What is Darwin's explanation for why island species resemble mainland
   species?"**
   - Tests: geographical distribution chapters (11-12), specific factual claim
   - Expected: precise answer with citations from island biogeography sections

5. **"Does Darwin discuss heredity mechanisms? What does he propose?"**
   - Tests: searching for something Darwin handles poorly (he had no knowledge
     of genetics), "I don't know fully" response quality
   - Expected: agent finds limited references to "laws of inheritance" but
     correctly notes Darwin lacked a mechanism

---

## Recommendation 2: Sherlock Holmes Short Stories

**What it tests: Mixed document collection with varied content, narrative search, and "not found" scenarios**

### Why This Corpus

The complete Sherlock Holmes short stories (56 stories across 5 collections)
create a large mixed-document workspace where:

- **Character and entity search** -- finding which story mentions a specific
  person, place, or object across dozens of files
- **Narrative vs. expository search** -- unlike the Federalist Papers (pure
  argument) or Darwin (scientific exposition), these are narratives where
  relevant information is embedded in dialogue and plot
- **"Not in the corpus" testing** -- with 56 stories that each have a distinct
  plot, it is easy to ask questions about events that do NOT happen, testing
  the agent's ability to say "I could not find this"
- **Scale** -- 56 files is enough to make brute-force reading impractical;
  the agent must use search effectively
- **Varied vocabulary** -- stories span crime, science, politics, romance,
  adventure, with domain-specific terms in each

### Source and Download

Five collections from Project Gutenberg, all public domain:

| Collection | eBook # | Plain Text URL | Stories | Size |
|---|---|---|---|---|
| The Adventures of Sherlock Holmes | 1661 | gutenberg.org/files/1661/1661-0.txt | 12 | 593 KB |
| The Memoirs of Sherlock Holmes | 834 | gutenberg.org/files/834/834-0.txt | 11 | 599 KB |
| The Return of Sherlock Holmes | 108 | gutenberg.org/files/108/108-0.txt | 13 | 703 KB |
| His Last Bow | 2350 | gutenberg.org/files/2350/2350-0.txt | 7 | 349 KB |
| The Case-Book of Sherlock Holmes | 69700 | gutenberg.org/files/69700/pg69700.txt | 12 | 472 KB |

- **Total:** 55 stories, ~2.7 MB raw (under 2 MB after stripping headers)
- **License:** Public domain

Note: "A Study in Scarlet" and "The Sign of the Four" are novels, not short
stories. Excluding them keeps the workspace uniform in document length and
avoids files that are much larger than the rest.

### Workspace Structure

Split each collection into individual story files:

```
test-data/sherlock-holmes/
  adventures-01-a-scandal-in-bohemia.txt
  adventures-02-the-red-headed-league.txt
  adventures-03-a-case-of-identity.txt
  ...
  memoirs-01-silver-blaze.txt
  memoirs-02-the-yellow-face.txt
  ...
  return-01-the-empty-house.txt
  ...
  last-bow-01-wisteria-lodge.txt
  ...
  casebook-01-the-illustrious-client.txt
  ...
```

### Splitting Script

Each collection uses Roman numeral headers (e.g., "I. A SCANDAL IN BOHEMIA",
"II. THE RED-HEADED LEAGUE"). Split on these markers:

```python
"""Split Sherlock Holmes collections into individual story files."""
import re
import urllib.request
from pathlib import Path

COLLECTIONS = {
    "adventures": {
        "url": "https://www.gutenberg.org/files/1661/1661-0.txt",
        "prefix": "adventures",
    },
    "memoirs": {
        "url": "https://www.gutenberg.org/files/834/834-0.txt",
        "prefix": "memoirs",
    },
    "return": {
        "url": "https://www.gutenberg.org/files/108/108-0.txt",
        "prefix": "return",
    },
    "last-bow": {
        "url": "https://www.gutenberg.org/files/2350/2350-0.txt",
        "prefix": "last-bow",
    },
    "casebook": {
        "url": "https://www.gutenberg.org/files/69700/pg69700.txt",
        "prefix": "casebook",
    },
}

def slugify(title):
    """Convert 'THE RED-HEADED LEAGUE' to 'the-red-headed-league'."""
    return re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')

output_dir = Path("test-data/sherlock-holmes")
output_dir.mkdir(parents=True, exist_ok=True)

for name, info in COLLECTIONS.items():
    text = urllib.request.urlopen(info["url"]).read().decode("utf-8")

    # Strip Gutenberg boilerplate
    for marker in ["*** START OF THE PROJECT GUTENBERG", "*** START OF THIS PROJECT GUTENBERG"]:
        if marker in text:
            text = text[text.index(marker):]
            text = text[text.index('\n'):]
            break
    for marker in ["*** END OF THE PROJECT GUTENBERG", "*** END OF THIS PROJECT GUTENBERG"]:
        if marker in text:
            text = text[:text.index(marker)]

    # Split on Roman numeral story headers
    # Pattern: line starts with Roman numerals, period, then TITLE IN CAPS
    parts = re.split(r'\n(?=[IVXLC]+\.\s+[A-Z])', text)

    story_num = 0
    for part in parts:
        # Check if this part starts with a story header
        header_match = re.match(r'[IVXLC]+\.\s+(.+)', part.strip())
        if header_match:
            story_num += 1
            title = header_match.group(1).strip()
            slug = slugify(title)
            filename = f"{info['prefix']}-{story_num:02d}-{slug}.txt"
            (output_dir / filename).write_text(part.strip())
            print(f"Wrote {filename}")
```

### Evaluation Questions

1. **"In which story does Holmes use a disguise to infiltrate a household?"**
   - Tests: searching across 55 files for a concept ("disguise") that appears
     in multiple stories, then identifying the specific one asked about
   - Expected: multiple hits (Scandal in Bohemia, others), agent must
     determine which ones involve household infiltration

2. **"What is the significance of the dog in 'Silver Blaze'?"**
   - Tests: targeted search within a specific file, finding the famous
     "dog that didn't bark" passage
   - Expected: precise citation of the "curious incident of the dog in the
     night-time" exchange

3. **"Does Sherlock Holmes ever travel to America in any of these stories?"**
   - Tests: broad search for a factual claim across the entire corpus
   - Expected: agent searches for "America" / "United States" across files,
     finds references (Noble Bachelor, others) and correctly reports

4. **"What poisons or toxins appear across the stories, and which stories
   feature them?"**
   - Tests: multi-file cross-referencing with domain-specific vocabulary
     (curare, belladonna, prussic acid, snake venom)
   - Expected: agent must search multiple terms, compile results from
     several stories

5. **"In which story does Watson get married?"**
   - Tests: specific factual question with a known answer (The Sign of the
     Four -- but that novel is excluded; the marriage is referenced in other
     stories). Tests whether agent can find indirect references or correctly
     note that the event itself is not depicted in this corpus.

---

## Recommendation 3: CIA World Factbook Country Profiles

**What it tests: Structured factual/reference material with verifiable answers**

### Why This Corpus

The CIA World Factbook contains structured, factual data about countries --
population, GDP, geography, government type, military, etc. This is
fundamentally different from the other corpora:

- **Factual precision** -- answers are specific numbers, dates, and names,
  not interpretive prose. Either the agent gets it right or wrong.
- **Structured data in text** -- each file follows the same template, testing
  whether the agent can navigate consistent document structure
- **Comparative queries** -- "which country has the highest X" requires
  searching across many files and comparing values
- **Numerical reasoning** -- population figures, GDP, area measurements
  require the agent to extract and reason about numbers
- **Null answers** -- not every country has data for every field, testing
  how the agent handles missing information

### Source and Download

- **Source:** github.com/factbook/factbook.json (auto-updated from CIA data)
- **URL:** https://github.com/factbook/factbook.json
- **Format:** JSON, one file per country, organized by region
- **Total countries:** 260 files
- **License:** Public domain (US government work)

### Workspace Structure

We do NOT want all 260 countries -- that is too many files for a test
workspace. Select 40 countries that provide good geographic and economic
diversity:

```
test-data/world-factbook/
  argentina.txt
  australia.txt
  bangladesh.txt
  brazil.txt
  canada.txt
  chile.txt
  china.txt
  colombia.txt
  cuba.txt
  egypt.txt
  ethiopia.txt
  france.txt
  germany.txt
  india.txt
  indonesia.txt
  iran.txt
  iraq.txt
  israel.txt
  italy.txt
  japan.txt
  kenya.txt
  mexico.txt
  morocco.txt
  new-zealand.txt
  nigeria.txt
  north-korea.txt
  norway.txt
  pakistan.txt
  peru.txt
  philippines.txt
  russia.txt
  saudi-arabia.txt
  south-africa.txt
  south-korea.txt
  spain.txt
  sweden.txt
  thailand.txt
  turkey.txt
  united-kingdom.txt
  united-states.txt
```

Each file is a plain-text rendering of the JSON profile, approximately
30-50 KB per file. Total workspace: ~1.5 MB.

### Conversion Script

```python
"""Download and convert CIA World Factbook country profiles to plain text."""
import json
import re
import urllib.request
from pathlib import Path

# GEC (FIPS) codes used by factbook.json -- NOT ISO codes
COUNTRIES = {
    "south-america/ar": "Argentina",
    "australia-oceania/as": "Australia",
    "south-asia/bg": "Bangladesh",
    "south-america/br": "Brazil",
    "north-america/ca": "Canada",
    "south-america/ci": "Chile",
    "east-n-southeast-asia/ch": "China",
    "south-america/co": "Colombia",
    "central-america-n-caribbean/cu": "Cuba",
    "africa/eg": "Egypt",
    "africa/et": "Ethiopia",
    "europe/fr": "France",
    "europe/gm": "Germany",
    "south-asia/in": "India",
    "east-n-southeast-asia/id": "Indonesia",
    "middle-east/ir": "Iran",
    "middle-east/iz": "Iraq",
    "middle-east/is": "Israel",
    "europe/it": "Italy",
    "east-n-southeast-asia/ja": "Japan",
    "africa/ke": "Kenya",
    "north-america/mx": "Mexico",
    "africa/mo": "Morocco",
    "australia-oceania/nz": "New Zealand",
    "africa/ni": "Nigeria",
    "east-n-southeast-asia/kn": "North Korea",
    "europe/no": "Norway",
    "south-asia/pk": "Pakistan",
    "south-america/pe": "Peru",
    "east-n-southeast-asia/rp": "Philippines",
    "europe/rs": "Russia",
    "middle-east/sa": "Saudi Arabia",
    "africa/sf": "South Africa",
    "east-n-southeast-asia/ks": "South Korea",
    "europe/sp": "Spain",
    "europe/sw": "Sweden",
    "east-n-southeast-asia/th": "Thailand",
    "middle-east/tu": "Turkey",
    "europe/uk": "United Kingdom",
    "north-america/us": "United States",
}

BASE_URL = "https://raw.githubusercontent.com/factbook/factbook.json/master"


def clean_html(text):
    """Remove HTML tags from factbook text fields."""
    return re.sub(r'<[^>]+>', '', text)


def json_to_text(data, country_name):
    """Convert a factbook JSON profile to readable plain text."""
    lines = [f"# {country_name}", ""]

    for section, content in data.items():
        if not isinstance(content, dict):
            continue
        lines.append(f"## {section}")
        lines.append("")

        for field, value in content.items():
            if isinstance(value, dict):
                if "text" in value:
                    lines.append(f"{field}: {clean_html(value['text'])}")
                else:
                    lines.append(f"### {field}")
                    for subfield, subval in value.items():
                        if isinstance(subval, dict) and "text" in subval:
                            lines.append(
                                f"  {subfield}: {clean_html(subval['text'])}"
                            )
                        elif isinstance(subval, str):
                            lines.append(f"  {subfield}: {clean_html(subval)}")
                    lines.append("")
            elif isinstance(value, str):
                lines.append(f"{field}: {clean_html(value)}")

        lines.append("")

    return "\n".join(lines)


def main():
    output_dir = Path("test-data/world-factbook")
    output_dir.mkdir(parents=True, exist_ok=True)

    for path, name in COUNTRIES.items():
        url = f"{BASE_URL}/{path}.json"
        try:
            raw = urllib.request.urlopen(url).read().decode("utf-8")
            data = json.loads(raw)
            text = json_to_text(data, name)
            slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
            filename = f"{slug}.txt"
            (output_dir / filename).write_text(text)
            print(f"Wrote {filename} ({len(text)} bytes)")
        except Exception as e:
            print(f"Failed to fetch {name} ({path}): {e}")


if __name__ == "__main__":
    main()
```

### Evaluation Questions

1. **"Which country in this collection has the largest population?"**
   - Tests: comparative search across 40 files, extracting and comparing
     numerical values
   - Expected: agent searches for "Population" fields, compares China and
     India, gives correct answer with citation

2. **"What type of government does Iran have, and who is the head of state?"**
   - Tests: navigating structured sections within a single file, extracting
     specific factual fields
   - Expected: precise answer citing the Government section of iran.txt

3. **"Which countries in this collection are landlocked?"**
   - Tests: searching for a geographic property across many files, where the
     answer is NOT a simple keyword (must check coastline = 0 or find
     "landlocked" in the geography text)
   - Expected: Ethiopia (and possibly others depending on the 40 selected)

4. **"What are the main exports of Brazil and how does its GDP compare to
   Argentina's?"**
   - Tests: cross-file comparison, extracting economic data, numerical
     reasoning
   - Expected: agent reads both files, extracts export and GDP data, presents
     comparison

5. **"Does the collection include information about climate change impacts
   on any of these countries?"**
   - Tests: searching for a topic that may or may not be present in the
     structured data, handling partial/tangential matches in environment
     sections
   - Expected: agent checks Environment sections, finds some references in
     "Environment - current issues" fields, qualifies the answer

---

## Summary Comparison

| Property | Federalist Papers | Origin of Species | Sherlock Holmes | World Factbook |
|---|---|---|---|---|
| Files | 85 | ~16 | ~55 | ~40 |
| Total size | 1.3 MB | ~950 KB | ~2.5 MB | ~1.5 MB |
| Genre | Political philosophy | Scientific treatise | Detective fiction | Reference/factual |
| Structure | Flat (one essay per file) | Hierarchical (long chapters) | Narrative (stories) | Tabular (structured fields) |
| Vocabulary | 18th-c. political prose | Scientific terminology | Varied/narrative | Factual/statistical |
| Answer type | Interpretive | Interpretive + factual | Factual + narrative | Precise factual |
| Key test | Thematic synthesis | Technical term search | Cross-document entity search | Numerical comparison |
| "I don't know" | Hard to test | Moderate | Easy (ask about absent plots) | Easy (ask about absent countries) |

### Retrieval Patterns Stressed by Each Corpus

**Federalist Papers (existing):**
- Search within a uniform vocabulary
- Synthesize arguments across related documents
- Author attribution

**Origin of Species (new):**
- Technical vocabulary precision (exact terms matter)
- Within-file navigation (long documents)
- Tracing arguments across chapters
- Handling a hierarchical document structure

**Sherlock Holmes (new):**
- Entity search across many files (people, places, objects)
- Finding information embedded in narrative/dialogue
- Filtering noise from a large mixed collection
- "Not found" responses for absent information
- Varied vocabulary across different story domains

**World Factbook (new):**
- Extracting values from structured/tabular text
- Comparative queries requiring multi-file numerical reasoning
- Navigating a consistent template across files
- Handling missing fields and partial data

---

## Setup Priority

Recommended implementation order:

1. **World Factbook** -- easiest to set up (JSON-to-text conversion is
   mechanical, answers are objectively verifiable, good for automated evals)
2. **Origin of Species** -- simple chapter split, good complement for
   technical vocabulary testing
3. **Sherlock Holmes** -- most files, most complex splitting logic, but
   highest value for testing cross-document search at scale

All three can be set up in under an hour using the scripts above.
