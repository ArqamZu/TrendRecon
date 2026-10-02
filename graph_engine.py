import os
import re
from pathlib import Path
from typing import List

import pandas as pd
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END

from state_models import (
    TrendReconState, FlawReport, Flaw, SpecDraft, SpecCritique,
)

from ddgs import DDGS

load_dotenv()

# Common column names across Kaggle Amazon / eBay review datasets
TEXT_COLS = ["reviews.text", "reviewText", "review_text", "Text", "text",
             "review", "Review", "content", "body", "review_body"]
TITLE_COLS = ["reviews.title", "summary", "Summary", "review_title", "title_review"]
META_COLS = ["name", "title", "Title", "product_title", "categories", "category",
             "product_name", "brand", "primaryCategories", "productTitle"]
RATING_COLS = ["reviews.rating", "rating", "Rating", "overall", "Score", "stars", "star_rating"]

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MAX_REVIEWS = int(os.getenv("MAX_REVIEWS", "120"))
MAX_REVIEW_CHARS = int(os.getenv("MAX_REVIEW_CHARS", "240"))
MAX_COMPETITOR_CHARS = int(os.getenv("MAX_COMPETITOR_CHARS", "6000"))
DEFAULT_DATASET = os.getenv("DATASET_PATH", "")

import time
import random
import threading
import hashlib

FALLBACK_MODELS = [
    m.strip() for m in os.getenv("GEMINI_FALLBACKS", "").split(",") if m.strip()
]
TRANSIENT = (
    "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED",
    "500", "504", "DEADLINE", "overloaded",
)
_models = {}
_call_cache = {}
_cache_lock = threading.Lock()

RPM_LIMIT = max(1, int(os.getenv("RPM_LIMIT", "5")))
MIN_INTERVAL = 60.0 / RPM_LIMIT
_rl_lock = threading.Lock()
_last_call = 0.0


def _throttle():
    """Ensure requests are spaced out across this process."""
    global _last_call
    with _rl_lock:
        wait = _last_call + MIN_INTERVAL - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()


def _get_llm(name: str):
    if name not in _models:
        _models[name] = ChatGoogleGenerativeAI(
            model=name,
            timeout=120,
            max_retries=0,
        )
    return _models[name]


def call_llm(prompt: str, schema=None, rounds: int = 2):
    """Use a small retry budget and cache identical requests for this process."""
    schema_name = schema.__name__ if schema else "text"
    cache_key = hashlib.sha256(
        f"{schema_name}\0{prompt}".encode("utf-8")
    ).hexdigest()

    with _cache_lock:
        cached = _call_cache.get(cache_key)
    if cached is not None:
        return schema.model_validate(cached) if schema else cached

    models = list(dict.fromkeys([MODEL_NAME, *FALLBACK_MODELS]))
    last_error = None

    for attempt in range(rounds):
        for name in models:
            _throttle()
            try:
                model = _get_llm(name)
                runnable = model.with_structured_output(schema) if schema else model
                result = runnable.invoke(prompt)
                cached_result = result.model_dump() if schema else result
                with _cache_lock:
                    _call_cache[cache_key] = cached_result
                return result
            except Exception as exc:
                last_error = exc
                message = str(exc)
                if "NOT_FOUND" in message or "404" in message:
                    continue
                if any(token in message for token in TRANSIENT):
                    continue
                raise

        if attempt + 1 < rounds:
            time.sleep(min(20, 3 * (2 ** attempt)) + random.uniform(0, 1))

    raise last_error


# ---------------- helpers ----------------
def _text(resp) -> str:
    """Gemini can return content as str or list of parts."""
    c = resp.content
    if isinstance(c, str):
        return c
    return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in c)


def _first_present(cols, available):
    return next((c for c in cols if c in available), None)


def _tokens(category: str) -> List[str]:
    toks = re.findall(r"[a-z0-9]+", category.lower())
    return [t[:-1] if len(t) > 3 and t.endswith("s") else t for t in toks]  # crude singularize


def _web_search(query: str, n: int = 8) -> List[str]:
    try:
        results = DDGS().text(query, max_results=n)
        return [f"{r.get('title', '')}: {r.get('body', '')}" for r in results]
    except Exception as e:
        return [f"(search failed: {e})"]


import functools

@functools.lru_cache(maxsize=1)
def _load_df(path: str) -> pd.DataFrame:
    src = Path(path)
    cache = src.with_suffix(".cache.pkl")
    if cache.exists() and cache.stat().st_mtime >= src.stat().st_mtime:
        return pd.read_pickle(cache)

    head = list(pd.read_csv(path, nrows=0).columns)
    text_col = _first_present(TEXT_COLS, head)
    if not text_col:
        raise ValueError(f"No review text column found. Columns: {head}")
    title_col = _first_present(TITLE_COLS, head)
    rating_col = _first_present(RATING_COLS, head)
    meta_cols = [c for c in META_COLS if c in head]

    usecols = list({c for c in [text_col, title_col, rating_col, *meta_cols] if c})
    df = pd.read_csv(path, usecols=usecols, on_bad_lines="skip", encoding_errors="ignore")

    if rating_col:  # complaints live in low ratings
        df = df[pd.to_numeric(df[rating_col], errors="coerce") <= 3]

    text = df[text_col].fillna("").astype(str).str.strip()
    if title_col:
        title = df[title_col].fillna("").astype(str)
        full = title + ". " + text
        hay = (title + " " + text)
    else:
        full, hay = text, text
    if meta_cols:
        hay = hay + " " + df[meta_cols].astype(str).agg(" ".join, axis=1)

    out = pd.DataFrame({"text": full.str.slice(0, 700), "hay": hay.str.lower()})
    out = out[text.str.len() >= 40].drop_duplicates(subset="text").reset_index(drop=True)
    out.to_pickle(cache)
    return out


def _load_csv_reviews(path: str, category: str) -> List[str]:
    df = _load_df(path)
    tokens = _tokens(category)

    mask = pd.Series(True, index=df.index)
    for t in tokens:
        mask &= df["hay"].str.contains(t, regex=False)
    sub = df[mask]

    if len(sub) < 50:  # too few matches -> relax to the last keyword
        sub = df[df["hay"].str.contains(tokens[-1], regex=False)]

    if len(sub) > MAX_REVIEWS:
        sub = sub.sample(MAX_REVIEWS, random_state=0)
    return sub["text"].tolist()


# ---------------- Node 1: Review Scraper ----------------
def review_scraper_node(state: TrendReconState) -> dict:
    category = state["category"]
    path = state.get("dataset_path") or DEFAULT_DATASET
    logs = list(state.get("logs", []))
    reviews, source = [], "web"

    if path and Path(path).exists():
        try:
            reviews = _load_csv_reviews(path, category)
            source = "csv"
            logs.append(f"Loaded {len(reviews)} matching reviews from {path}")
        except Exception as e:
            logs.append(f"CSV load failed ({e}); falling back to live web.")
    else:
        logs.append("Dataset not found; using live web search.")

    if len(reviews) < 30:
        logs.append("Too few dataset reviews - scraping live web snippets instead.")
        queries = [
            f"{category} common complaints reviews",
            f"{category} broke after months reddit",
            f"{category} worst problems 1 star reviews",
            f"best {category} problems buyers regret",
        ]
        web = []
        for q in queries:
            web += _web_search(q, 10)
        reviews = reviews + web
        source = "web" if source != "csv" else "csv+web"
        logs.append(f"Web scrape added {len(web)} snippets.")

    return {"reviews": reviews, "review_source": source,
            "review_count": len(reviews), "logs": logs}


# ---------------- Node 2: Flaw Finder (map-reduce over Gemini's long context) ----------------
from concurrent.futures import ThreadPoolExecutor

def flaw_finder_node(state: TrendReconState) -> dict:
    reviews = state["reviews"]
    category = state["category"]
    logs = list(state.get("logs", []))

    if not reviews:
        raise RuntimeError(
            "No reviews were loaded. Check the category and dataset."
        )

    # Deterministic sampling makes reruns reproducible and bounds prompt size.
    sample_size = min(MAX_REVIEWS, len(reviews))
    seed = int(hashlib.sha256(category.lower().encode()).hexdigest()[:8], 16)
    sample = random.Random(seed).sample(reviews, sample_size)
    sample = [str(review).strip()[:MAX_REVIEW_CHARS] for review in sample]
    sample = [review for review in sample if review]
    joined = "\n".join(f"- {review}" for review in sample)

    prompt = f"""You are a product-defect analyst for "{category}".
Analyze these real buyer reviews. Ignore shipping, price, and customer-service
complaints. Focus on product flaws such as quality, freshness, packaging,
durability, or consistency.

Return up to 3 distinct recurring flaws, ranked by frequency and severity.
Include 2 short verbatim quotes per flaw. Do not invent quotes.

REVIEWS:
{joined}"""

    result = call_llm(prompt, FlawReport)
    top = result.top_flaws[:3]
    if not top:
        raise RuntimeError("Gemini returned an empty flaw list.")

    logs.append(
        f"Flaw finder analyzed {len(sample)} sampled reviews in 1 Gemini call."
    )
    logs.append("Top flaws: " + " | ".join(f.title for f in top))
    return {"flaws": top, "logs": logs}


# ---------------- Node 3a: Competitor Research ----------------
def competitor_research_node(state: TrendReconState) -> dict:
    category = state["category"]
    logs = list(state.get("logs", []))
    snippets = []
    for q in [
        f"top selling {category} specifications materials",
        f"{category} user manual specifications weight capacity warranty",
        f"{category} product datasheet technical specs",
    ]:
        snippets += _web_search(q, 6)
    context = "\n".join(f"- {s}" for s in snippets)[:12000]
    logs.append(f"Collected {len(snippets)} competitor spec/manual snippets.")
    return {"competitor_context": context, "iteration": 0, "logs": logs}


# ---------------- Node 3b: Spec Drafter ----------------
def spec_drafter_node(state: TrendReconState) -> dict:
    logs = list(state.get("logs", []))
    flaws_txt = "\n".join(
        f"{i}. {f.title} (sev {f.severity}): {f.description}" for i, f in enumerate(state["flaws"], 1)
    )
    critique = state.get("critique")
    feedback = ""
    if critique and not critique.approved:
        feedback = ("\n\nPREVIOUS DRAFT WAS REJECTED. Fix these:\n"
                    + "\n".join(f"- {x}" for x in critique.issues + critique.suggestions))

    prompt = f"""You are a senior product engineer designing a new variant of: {state['category']}.

REAL BUYER FLAWS TO ELIMINATE:
{flaws_txt}

COMPETITOR SPECS / MANUAL EXCERPTS (baseline to beat):
{state['competitor_context']}
{feedback}

Draft revised engineering specs. Every flaw must map to at least one spec with concrete
materials, dimensions, load/cycle ratings or tolerances, and a competitor baseline for comparison."""
    draft = call_llm(prompt, SpecDraft)
    logs.append(f"Drafted {len(draft.specs)} spec items (iteration {state.get('iteration', 0) + 1}).")
    return {"spec_draft": draft, "iteration": state.get("iteration", 0) + 1, "logs": logs}


# ---------------- Node 3c: Spec Critic ----------------
def spec_drafter_node(state: TrendReconState) -> dict:
    logs = list(state.get("logs", []))
    flaws_txt = "\n".join(
        f"{i}. {flaw.title} (severity {flaw.severity}/5): {flaw.description}"
        for i, flaw in enumerate(state["flaws"], 1)
    )
    context = state.get("competitor_context", "")[:MAX_COMPETITOR_CHARS]

    prompt = f"""You are a senior product engineer designing a new variant of
"{state['category']}".

BUYER FLAWS:
{flaws_txt}

COMPETITOR RESEARCH (may be incomplete; do not invent baselines):
{context}

Create measurable engineering specifications that address every flaw.
Include component, proposed spec, competitor baseline, flaw addressed,
rationale, and estimated unit-cost impact. Use cautious language when
research does not provide a reliable baseline."""

    draft = call_llm(prompt, SpecDraft)

    covered = " ".join(
        f"{item.solves_flaw} {item.component} {item.proposed_spec}"
        for item in draft.specs
    ).lower()
    unaddressed = [
        flaw.title for flaw in state["flaws"]
        if flaw.title.lower() not in covered
    ]
    if unaddressed:
        logs.append(
            "Local coverage check: verify specs for "
            + ", ".join(unaddressed)
        )

    logs.append(f"Drafted {len(draft.specs)} spec items in 1 Gemini call.")
    return {"spec_draft": draft, "iteration": 1, "logs": logs}


def brief_generator_node(state: TrendReconState) -> dict:
    logs = list(state.get("logs", []))
    flaws = state["flaws"]
    specs = state["spec_draft"].specs
    draft = state["spec_draft"]

    flaw_section = "\n".join(
        f"### {i}. {flaw.title}: severity {flaw.severity}/5\n"
        f"{flaw.description}\n\n"
        f"Frequency estimate: {flaw.frequency_estimate}\n\n"
        + "\n".join(f"> {quote}" for quote in flaw.example_quotes)
        for i, flaw in enumerate(flaws, 1)
    )

    spec_rows = "\n".join(
        f"| {item.component} | {item.competitor_baseline} | "
        f"{item.proposed_spec} | {item.solves_flaw} |"
        for item in specs
    )

    brief = f"""# Product Strategy Brief: {state['category']}

## Executive Summary
A proposed product variant focused on addressing the recurring customer
issues identified in the available review sample. Specifications and
competitor baselines should be validated before production.

## Market Insight & Voice of the Customer
Analysis covered **{state['review_count']} reviews** from **{state['review_source']}**.
The findings below reflect the available sample and are not a market-wide
estimate.

## Top Product Flaws
{flaw_section}

## Engineering Specification Sheet
| Component | Competitor baseline | Proposed specification | Flaw addressed |
|---|---|---|---|
{spec_rows}

## Estimated Cost Impact
{draft.estimated_cost_impact}

## Competitive Positioning & Potential Differentiators
- Design around the specific recurring flaws listed above.
- Validate competitor comparisons against current product documentation.
- Treat measurable, testable specifications as product proof points.

## Draft Marketing Copy
**Headline:** Designed around the details customers notice.

**Tagline:** Built to address real-world product frustrations.

- Focus on the documented product improvements.
- Use only specifications verified by testing.
- Avoid unsupported performance or durability claims.
- Validate claims against the final production design.
- Share evidence for any comparative claims.

**Short ad:** A product concept shaped by customer feedback, with proposed
engineering changes targeted at the issues buyers report most often.

## Production & Quality-Control Checklist
- Confirm each specification is measurable and testable.
- Verify competitor baselines against primary sources.
- Test components against the proposed ratings and tolerances.
- Check production samples for consistency.
- Substantiate marketing claims before publication.

## Risks & Next Steps
- Review evidence quality and confirm that quotes are representative.
- Validate proposed specs and cost estimates with suppliers and engineers.
- Run prototype and quality-control testing before making performance claims.
"""

    logs.append("Product brief assembled locally; no Gemini call used.")
    return {"final_brief": brief, "logs": logs}


def build_graph():
    graph_builder = StateGraph(TrendReconState)
    graph_builder.add_node("review_scraper", review_scraper_node)
    graph_builder.add_node("flaw_finder", flaw_finder_node)
    graph_builder.add_node("competitor_research", competitor_research_node)
    graph_builder.add_node("spec_drafter", spec_drafter_node)
    graph_builder.add_node("brief_generator", brief_generator_node)

    graph_builder.add_edge(START, "review_scraper")
    graph_builder.add_edge("review_scraper", "flaw_finder")
    graph_builder.add_edge("flaw_finder", "competitor_research")
    graph_builder.add_edge("competitor_research", "spec_drafter")
    graph_builder.add_edge("spec_drafter", "brief_generator")
    graph_builder.add_edge("brief_generator", END)
    return graph_builder.compile()


graph = build_graph()