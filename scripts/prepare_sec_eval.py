"""Download SEC 10-K filings and generate eval questions from XBRL data.

Usage:
    uv run python scripts/prepare_sec_eval.py
    uv run python scripts/prepare_sec_eval.py --num-questions 20 --seed 42

Downloads ~25 large-cap 10-K filings from EDGAR, extracts ground-truth
financial facts via the XBRL API, and generates template-based questions
with verifiable answers. Re-run every ~6 months for fresh data.
"""

from __future__ import annotations

import argparse
import json
import random
import time
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup, Tag

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "test-data" / "sec-10k"

# SEC EDGAR requires a User-Agent with contact info.
SEC_USER_AGENT = "LLMHarness research@example.com"

# (ticker, CIK zero-padded to 10 digits, display name)
COMPANIES = [
    ("AAPL", "0000320193", "Apple"),
    ("MSFT", "0000789019", "Microsoft"),
    ("AMZN", "0001018724", "Amazon"),
    ("GOOGL", "0001652044", "Alphabet"),
    ("META", "0001326801", "Meta Platforms"),
    ("NVDA", "0001045810", "NVIDIA"),
    ("TSLA", "0001318605", "Tesla"),
    ("BRK-B", "0001067983", "Berkshire Hathaway"),
    ("JPM", "0000019617", "JPMorgan Chase"),
    ("JNJ", "0000200406", "Johnson & Johnson"),
    ("V", "0001403161", "Visa"),
    ("PG", "0000080424", "Procter & Gamble"),
    ("UNH", "0000731766", "UnitedHealth Group"),
    ("HD", "0000354950", "Home Depot"),
    ("MA", "0001141391", "Mastercard"),
    ("XOM", "0000034088", "Exxon Mobil"),
    ("CVX", "0000093410", "Chevron"),
    ("PFE", "0000078003", "Pfizer"),
    ("ABBV", "0001551152", "AbbVie"),
    ("KO", "0000021344", "Coca-Cola"),
    ("PEP", "0000077476", "PepsiCo"),
    ("COST", "0000909832", "Costco"),
    ("WMT", "0000104169", "Walmart"),
    ("DIS", "0001744489", "Walt Disney"),
    ("INTC", "0000050863", "Intel"),
]

# XBRL concept names to try for each metric — companies use different tags.
FACT_DEFINITIONS: dict[str, dict] = {
    "revenue": {
        "concepts": [
            ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
            ("us-gaap", "Revenues"),
            ("us-gaap", "SalesRevenueNet"),
            ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
        ],
        "label": "total revenue",
    },
    "net_income": {
        "concepts": [
            ("us-gaap", "NetIncomeLoss"),
            ("us-gaap", "ProfitLoss"),
        ],
        "label": "net income",
    },
    "total_assets": {
        "concepts": [
            ("us-gaap", "Assets"),
        ],
        "label": "total assets",
    },
    "employees": {
        "concepts": [
            ("dei", "EntityNumberOfEmployees"),
        ],
        "label": "number of employees",
    },
}


# ---------------------------------------------------------------------------
# SEC API helpers
# ---------------------------------------------------------------------------


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": SEC_USER_AGENT})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    time.sleep(0.15)
    return data


def _fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": SEC_USER_AGENT})
    with urllib.request.urlopen(req) as resp:
        data = resp.read()
    time.sleep(0.15)
    return data


def find_latest_10k(cik: str) -> tuple[str, str, str] | None:
    """Return (accession, primary_document, filing_date) for the latest 10-K."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    submissions = _fetch_json(url)
    recent = submissions["filings"]["recent"]
    for i, form in enumerate(recent["form"]):
        if form == "10-K":
            return (
                recent["accessionNumber"][i],
                recent["primaryDocument"][i],
                recent["filingDate"][i],
            )
    return None


def _strip_xbrl_noise(soup: BeautifulSoup) -> None:
    """Remove iXBRL metadata elements that pollute get_text() output."""
    for tag_name in ("ix:hidden", "ix:header"):
        for el in soup.find_all(tag_name):
            el.decompose()
    for el in soup.find_all(style=lambda v: v and "display:none" in v):
        el.decompose()


def _table_to_text(table: Tag) -> str:
    """Convert an HTML table to tab-separated text."""
    rows = []
    for tr in table.find_all("tr"):
        cells = [
            td.get_text(separator=" ", strip=True)
            for td in tr.find_all(["td", "th"])
        ]
        if any(cells):
            rows.append("\t".join(cells))
    return "\n".join(rows)


def download_filing_text(cik: str, accession: str, primary_doc: str) -> str:
    """Download filing HTML and extract readable plain text."""
    cik_num = str(int(cik))
    accession_flat = accession.replace("-", "")
    url = (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{cik_num}/{accession_flat}/{primary_doc}"
    )
    html = _fetch_bytes(url)
    soup = BeautifulSoup(html, "html.parser")
    _strip_xbrl_noise(soup)

    # Replace tables with tab-separated text to preserve column alignment
    for table in soup.find_all("table"):
        table.replace_with(soup.new_string("\n" + _table_to_text(table) + "\n"))

    return soup.get_text(separator="\n", strip=True)


# ---------------------------------------------------------------------------
# XBRL fact extraction
# ---------------------------------------------------------------------------


def _extract_latest_annual_value(
    company_facts: dict, taxonomy: str, concept: str
) -> tuple[int, int] | None:
    """Return (value, fiscal_year) for the most recent 10-K annual entry."""
    concept_data = (
        company_facts.get("facts", {}).get(taxonomy, {}).get(concept, {})
    )
    for entries in concept_data.get("units", {}).values():
        annual = [
            e
            for e in entries
            if e.get("form") == "10-K" and e.get("fp") == "FY"
        ]
        if annual:
            annual.sort(key=lambda e: e.get("end", ""), reverse=True)
            return int(annual[0]["val"]), int(annual[0]["fy"])
    return None


def extract_facts(cik: str) -> dict[str, tuple[int, int]]:
    """Return {fact_name: (value, fiscal_year)} for available XBRL facts."""
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    company_facts = _fetch_json(url)

    results: dict[str, tuple[int, int]] = {}
    for fact_name, defn in FACT_DEFINITIONS.items():
        for taxonomy, concept in defn["concepts"]:
            found = _extract_latest_annual_value(
                company_facts, taxonomy, concept
            )
            if found:
                results[fact_name] = found
                break
    return results


# ---------------------------------------------------------------------------
# Question generation
# ---------------------------------------------------------------------------


def format_dollar_variants(value: int) -> list[str]:
    """Generate plausible text representations of a dollar amount."""
    v = abs(value)
    variants = [f"{v:,}"]

    if v >= 1_000_000_000:
        billions = v / 1_000_000_000
        variants.append(f"{billions:.1f} billion")
        variants.append(f"{billions:.1f}B")
        if billions >= 10:
            variants.append(f"{round(billions)} billion")

    if v >= 1_000_000:
        millions = v / 1_000_000
        variants.append(f"{millions:,.0f} million")

    return variants


def format_count_variants(value: int) -> list[str]:
    """Generate plausible text representations of a count (e.g. employees)."""
    variants = [f"{value:,}"]
    if value >= 1000:
        thousands = value / 1000
        variants.append(f"{thousands:,.0f},000")
    return variants


def _generate_single_fact_questions(
    company_data: dict[str, dict],
) -> list[dict]:
    questions = []
    for info in company_data.values():
        for fact_name, (value, fy) in info["facts"].items():
            defn = FACT_DEFINITIONS[fact_name]
            is_dollar = fact_name != "employees"
            variants = (
                format_dollar_variants(value)
                if is_dollar
                else format_count_variants(value)
            )
            questions.append(
                {
                    "text": (
                        f"What was {info['name']}'s {defn['label']} "
                        f"in fiscal year {fy}?"
                    ),
                    "category": "single_fact",
                    "must_contain": [info["name"].lower()],
                    "must_contain_any": variants,
                    "min_tool_calls": 1,
                }
            )
    return questions


def _generate_comparison_questions(
    company_data: dict[str, dict],
) -> list[dict]:
    questions = []
    tickers = list(company_data.keys())

    for fact_name in ("revenue", "net_income", "total_assets"):
        with_fact = [
            t for t in tickers if fact_name in company_data[t]["facts"]
        ]
        for i, t1 in enumerate(with_fact):
            for t2 in with_fact[i + 1 :]:
                v1, fy1 = company_data[t1]["facts"][fact_name]
                v2, fy2 = company_data[t2]["facts"][fact_name]
                if fy1 != fy2:
                    continue
                winner = t1 if v1 > v2 else t2
                winner_name = company_data[winner]["name"]
                defn = FACT_DEFINITIONS[fact_name]
                questions.append(
                    {
                        "text": (
                            f"Which company had higher {defn['label']} in "
                            f"fiscal year {fy1}, {company_data[t1]['name']} "
                            f"or {company_data[t2]['name']}?"
                        ),
                        "category": "comparison",
                        "must_contain": [winner_name.lower()],
                        "must_contain_any": [],
                        "min_tool_calls": 2,
                    }
                )
    return questions


def _generate_multi_doc_questions(
    company_data: dict[str, dict],
) -> list[dict]:
    questions = []
    tickers = list(company_data.keys())

    for fact_name in ("revenue", "net_income", "total_assets", "employees"):
        with_fact = [
            t for t in tickers if fact_name in company_data[t]["facts"]
        ]
        if len(with_fact) < 3:
            continue
        best = max(
            with_fact,
            key=lambda t: company_data[t]["facts"][fact_name][0],
        )
        defn = FACT_DEFINITIONS[fact_name]
        questions.append(
            {
                "text": (
                    f"Which company in the dataset had the highest "
                    f"{defn['label']}?"
                ),
                "category": "multi_doc",
                "must_contain": [company_data[best]["name"].lower()],
                "must_contain_any": [],
                "min_tool_calls": 3,
            }
        )
    return questions


def generate_all_candidate_questions(
    company_data: dict[str, dict],
) -> list[dict]:
    return (
        _generate_single_fact_questions(company_data)
        + _generate_comparison_questions(company_data)
        + _generate_multi_doc_questions(company_data)
    )


def sample_balanced(
    candidates: list[dict], n: int, rng: random.Random
) -> list[dict]:
    """Sample n questions, ensuring representation from each category."""
    by_category: dict[str, list[dict]] = {}
    for q in candidates:
        by_category.setdefault(q["category"], []).append(q)

    selected: list[dict] = []
    per_category = max(1, n // len(by_category))

    for questions in by_category.values():
        rng.shuffle(questions)
        selected.extend(questions[:per_category])

    already_selected = {id(q) for q in selected}
    remaining = [q for q in candidates if id(q) not in already_selected]
    rng.shuffle(remaining)
    selected.extend(remaining[: n - len(selected)])

    selected = selected[:n]
    rng.shuffle(selected)
    return selected


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download SEC 10-K filings and generate eval questions"
    )
    parser.add_argument(
        "--num-questions",
        type=int,
        default=15,
        help="Number of questions to generate (default: 15)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for question selection (default: random)",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)  # noqa: S311

    # Phase 1 & 2: Download filings and extract XBRL facts
    company_data: dict[str, dict] = {}

    for ticker, cik, name in COMPANIES:
        print(f"  {ticker}...", end=" ", flush=True)

        try:
            filing = find_latest_10k(cik)
            if not filing:
                print("no 10-K found, skipping")
                continue
            accession, primary_doc, filing_date = filing

            text = download_filing_text(cik, accession, primary_doc)
            out_path = OUTPUT_DIR / f"{ticker.lower()}-{filing_date[:4]}.txt"
            out_path.write_text(text)

            facts = extract_facts(cik)
            if not facts:
                print(f"filed {filing_date}, no XBRL facts")
                continue

            company_data[ticker] = {"name": name, "facts": facts}
            fact_names = ", ".join(facts.keys())
            print(f"filed {filing_date}, facts: {fact_names}")

        except Exception as exc:
            print(f"error: {exc}")
            continue

    print(f"\nDownloaded {len(company_data)} companies to {OUTPUT_DIR}")

    if not company_data:
        print("No data to generate questions from — check errors above.")
        return

    # Phase 3: Generate and sample questions
    all_questions = generate_all_candidate_questions(company_data)
    selected = sample_balanced(all_questions, args.num_questions, rng)

    questions_path = OUTPUT_DIR / "questions.json"
    questions_path.write_text(json.dumps(selected, indent=2))

    categories: dict[str, int] = {}
    for q in selected:
        categories[q["category"]] = categories.get(q["category"], 0) + 1

    print(
        f"Wrote {len(selected)} questions to {questions_path}\n"
        f"Categories: {categories}"
    )


if __name__ == "__main__":
    main()
