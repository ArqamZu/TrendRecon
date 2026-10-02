# TrendRecon

**Turn customer feedback into product opportunities.**

TrendRecon is a Streamlit app that analyzes product-review evidence, identifies recurring product flaws, researches competitor specifications, and creates an engineering concept and product strategy brief.

## Features

- Analyze reviews from a local CSV dataset or web-search snippets.
- Identify up to three recurring product flaws with example quotes.
- Research competitor specifications and product documentation.
- Draft engineering specifications linked to customer issues.
- Generate and download a Markdown strategy brief.
- Cache identical Gemini requests during the running process.

The usual run makes two Gemini calls: one for flaw analysis and one for the specification draft. Retries or configured fallback models can increase that number.

## Requirements

- Python 3.10 or later
- A Google Gemini API key
- Internet access for Gemini and web search

## Quick start

Clone the repository and open its directory:

```bash
git clone <https://github.com/ArqamZu/TrendRecon.git>
cd Langchain-project
```

Create and activate a virtual environment on Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

Create a local environment file and add your Gemini API key:

```bash
cp .env.example .env
```

Edit `.env`, then start Streamlit:

```bash
streamlit run app.py
```

## Configuration

| Variable | Required | Default | Purpose |
|---|---:|---|---|
| `GOOGLE_API_KEY` | Yes | — | Gemini API key |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Gemini model name |
| `GEMINI_FALLBACKS` | No | Empty | Comma-separated fallback model names |
| `DATASET_PATH` | No | Empty | Default path to a review CSV |
| `MAX_REVIEWS` | No | `120` | Maximum reviews sampled for flaw analysis |
| `MAX_REVIEW_CHARS` | No | `240` | Maximum characters per review sent to Gemini |
| `MAX_COMPETITOR_CHARS` | No | `6000` | Competitor context limit for specification drafting |
| `RPM_LIMIT` | No | `5` | Minimum spacing between Gemini requests |

Example:

```dotenv
GOOGLE_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.5-flash
DATASET_PATH=/path/to/reviews.csv
MAX_REVIEWS=120
RPM_LIMIT=5
```

Keep `.env` private; do not commit API keys to GitHub.

## Review CSV format

The app looks for common review text columns, including `reviews.text`, `reviewText`, `review_text`, `text`, and `review`. It can also use common rating, title, and product metadata columns.

When a rating column is available, the loader filters for ratings of 3 or lower. It tries to match category words against review and product metadata. If too few CSV reviews match, it supplements them with web-search snippets.

Set `DATASET_PATH` in `.env` to use a default dataset. The app does not ask users to enter a local file path.

## Workflow

1. Collect review evidence from the configured CSV and/or web search.
2. Sample a bounded number of reviews and ask Gemini to find recurring flaws.
3. Search for competitor specifications and product documentation.
4. Ask Gemini to draft specifications addressing the identified flaws.
5. Assemble a Markdown product strategy brief locally.

The review metric reflects collected reviews; flaw analysis samples up to `MAX_REVIEWS`.

## Project structure

```text
.
├── app.py             # Streamlit interface
├── graph_engine.py    # Review collection, LangGraph workflow, Gemini calls
├── state_models.py    # Pydantic output schemas and graph state
```

## Important limitations

- Web-search snippets are not a verified or representative review dataset.
- Review sampling and search results can affect the findings.
- Competitor baselines, cost estimates, and generated specifications require human and supplier validation.
- Do not treat generated marketing claims or engineering proposals as verified facts.
- Gemini quotas and availability depend on your Google AI account and model access.

## Troubleshooting

**Missing API key:** Check that `.env` exists in the project root and contains `GOOGLE_API_KEY=...`.

**Quota or rate-limit errors:** Lower `MAX_REVIEWS`, reduce repeated runs, or wait for the provider’s quota window to reset. Fallback models may have separate availability and limits.

**No CSV reviews found:** Check `DATASET_PATH`, confirm the CSV has a supported review-text column, and ensure product metadata or review text contains category keywords.

**Start the app from the project directory:** Streamlit and `.env` loading use the current working directory.
project.

