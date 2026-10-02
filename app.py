import hashlib
import os
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

st.set_page_config(
    page_title="TrendRecon | Product Intelligence",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

load_dotenv()


def get_setting(name: str) -> str:
    value = os.getenv(name, "")
    if value:
        return value
    try:
        return str(st.secrets[name])
    except Exception:
        return ""


api_key = get_setting("GOOGLE_API_KEY")
if not api_key:
    st.error("Set GOOGLE_API_KEY in your `.env` file or Streamlit Cloud Secrets.")
    st.stop()

os.environ["GOOGLE_API_KEY"] = api_key

dataset_url = get_setting("DATASET_URL")
if dataset_url and not os.getenv("DATASET_PATH"):
    cache_id = hashlib.sha256(dataset_url.encode("utf-8")).hexdigest()[:16]
    dataset_path = Path("/tmp") / f"trendrecon-{cache_id}.csv"
    partial_path = dataset_path.with_suffix(".part")

    if not dataset_path.exists():
        try:
            with requests.get(dataset_url, stream=True, timeout=(20, 180)) as response:
                response.raise_for_status()
                with partial_path.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            output.write(chunk)

            start = partial_path.read_bytes()[:512].lstrip().lower()
            if start.startswith((b"<!doctype html", b"<html")):
                raise ValueError(
                    "DATASET_URL returned an HTML page, not the CSV. "
                    "Configure a direct download URL."
                )

            partial_path.replace(dataset_path)
        except Exception as exc:
            partial_path.unlink(missing_ok=True)
            st.error(f"Could not download the review dataset: {exc}")
            st.stop()

    os.environ["DATASET_PATH"] = str(dataset_path)

# Import only after DATASET_PATH and GOOGLE_API_KEY are configured.
from graph_engine import DEFAULT_DATASET, graph  # noqa: E402

dataset_url = os.getenv("DATASET_URL")
if not dataset_url:
    try:
        dataset_url = st.secrets["DATASET_URL"]
    except (KeyError, FileNotFoundError):
        dataset_url = ""

if dataset_url and not os.getenv("DATASET_PATH"):
    cache_name = hashlib.sha256(dataset_url.encode("utf-8")).hexdigest()[:16]
    dataset_path = Path("/tmp") / f"trendrecon-{cache_name}.csv"

    if not dataset_path.exists():
        partial_path = dataset_path.with_suffix(".part")
        try:
            with requests.get(dataset_url, stream=True, timeout=(20, 120)) as response:
                response.raise_for_status()
                with partial_path.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            output.write(chunk)

            if partial_path.read_bytes()[:512].lstrip().lower().startswith(
                (b"<!doctype html", b"<html")
            ):
                raise ValueError("The dataset URL returned an HTML page, not a CSV.")

            partial_path.replace(dataset_path)
        except Exception:
            partial_path.unlink(missing_ok=True)
            raise

    os.environ["DATASET_PATH"] = str(dataset_path)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap');

    :root {
      --ink: #17221f;
      --muted: #718078;
      --paper: #f5f7f4;
      --line: #e4e9e3;
      --green: #167653;
      --green-dark: #10583e;
      --lime: #c8f169;
    }

    .stApp { background: var(--paper); color: var(--ink); }
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    h1, h2, h3 { font-family: 'Manrope', sans-serif; letter-spacing: -.04em; }
    .block-container { max-width: 1320px; padding: 2rem 3rem 4rem; }

    [data-testid="stSidebar"] {
      background: #fff;
      border-right: 1px solid var(--line);
    }
    [data-testid="stSidebar"] .block-container { padding: 1.8rem 1.35rem; }

    .brand {
      display: flex; align-items: center; gap: .7rem;
      margin: .2rem 0 2.6rem;
      color: var(--ink); font-family: 'Manrope', sans-serif;
      font-size: 1.1rem; font-weight: 800; letter-spacing: -.04em;
    }
    .brand-mark {
      display: grid; place-items: center; width: 34px; height: 34px;
      border-radius: 10px; color: #173426; background: var(--lime);
    }
    .sidebar-label, .eyebrow {
      color: var(--green); text-transform: uppercase;
      letter-spacing: .14em; font-size: .7rem; font-weight: 800;
    }
    .sidebar-step {
      padding: .8rem 0; border-bottom: 1px solid var(--line);
      color: #435149; font-size: .9rem;
    }
    .sidebar-step span { color: var(--green); font-weight: 800; margin-right: .45rem; }

    .hero {
      position: relative; isolation: isolate; overflow: hidden;
      padding: 2.6rem 2.8rem; margin: .15rem 0 2rem;
      border-radius: 22px; color: #fff;
      background: linear-gradient(115deg, #132820, #1b4938 62%, #23664d);
      box-shadow: 0 16px 38px rgba(23, 57, 43, .12);
    }
    .hero:after {
      content: ""; position: absolute; z-index: -1; pointer-events: none;
      width: 280px; height: 280px; right: -75px; top: -150px;
      border-radius: 50%; border: 1px solid rgba(216,255,184,.2);
      box-shadow: 0 0 0 34px rgba(216,255,184,.035),
                  0 0 0 70px rgba(216,255,184,.025);
    }
    .hero-tag {
      display: inline-block; padding: .4rem .7rem; margin-bottom: 1.05rem;
      border: 1px solid rgba(220,255,233,.25); border-radius: 999px;
      color: #e5f5e9; background: rgba(255,255,255,.07);
      font-size: .72rem; font-weight: 700; letter-spacing: .08em;
    }
    .hero h1 {
      position: relative; z-index: 1; max-width: 740px;
      margin: 0; color: #fff; font-size: clamp(2rem, 4vw, 3.2rem);
      line-height: 1.08;
    }
    .hero p {
      position: relative; z-index: 1; max-width: 610px;
      margin: 1rem 0 0; color: #d5e5dc;
      font-size: 1rem; line-height: 1.65;
    }

    .workspace-title { margin: 0 0 .25rem; font-size: 1.65rem; }
    .workspace-copy { color: var(--muted); margin: 0 0 1.2rem; }
    [data-testid="stForm"] {
      padding: 1.4rem 1.5rem 1.2rem;
      border: 1px solid var(--line); border-radius: 16px;
      background: #fff; box-shadow: 0 8px 24px rgba(24, 43, 34, .04);
    }
    [data-testid="stTextInput"] input {
      min-height: 2.8rem; border-radius: 9px; background: #fff;
    }
    div.stButton > button[kind="primary"],
    div[data-testid="stFormSubmitButton"] button {
      min-height: 2.85rem; border-radius: 9px;
      background: var(--green); border: 1px solid var(--green);
      color: #fff; font-weight: 700;
      transition: transform .15s ease, box-shadow .15s ease;
    }
    div.stButton > button[kind="primary"]:hover,
    div[data-testid="stFormSubmitButton"] button:hover {
      background: var(--green-dark); border-color: var(--green-dark);
      box-shadow: 0 7px 18px rgba(21, 122, 91, .2);
      transform: translateY(-1px);
    }
    [data-testid="stMetric"] {
      padding: 1.05rem 1.2rem; border: 1px solid var(--line);
      border-radius: 14px; background: #fff;
      box-shadow: 0 5px 18px rgba(24, 43, 34, .035);
    }
    [data-testid="stMetricLabel"] { color: var(--muted); }
    [data-testid="stMetricValue"] {
      color: var(--ink); font-family: 'Manrope', sans-serif; font-weight: 800;
    }
    [data-testid="stTabs"] [role="tab"] { padding: .75rem 1rem; font-weight: 600; }
    [data-testid="stTabs"] [aria-selected="true"] { color: var(--green) !important; }
    .source-pill {
      display: inline-block; padding: .35rem .68rem; margin-top: .4rem;
      border: 1px solid var(--line); border-radius: 999px;
      background: #fff; color: var(--muted); font-size: .78rem; font-weight: 700;
    }
    [data-testid="stHeader"] {
    display: none;
    }

    .block-container {
    padding-top: 1.5rem;
    }

    [data-testid="stTextInput"] label {
    color: #17221f !important;
    }

    [data-testid="stTextInput"] input {
    color: #17221f !important;
    background: #fff !important;
    }

    [data-testid="stTextInput"] input::placeholder {
    color: #718078 !important;
    opacity: 1;
    }    
    .stAlert { border-radius: 12px; }

    @media (max-width: 760px) {
      .block-container { padding: 1.2rem 1rem 3rem; }
      .hero { padding: 1.7rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown(
        '<div class="brand"><span class="brand-mark">◈</span> TrendRecon</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="sidebar-label">Your workflow</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="sidebar-step"><span>01</span> Review evidence</div>
        <div class="sidebar-step"><span>02</span> Customer pain points</div>
        <div class="sidebar-step"><span>03</span> Product specifications</div>
        <div class="sidebar-step"><span>04</span> Strategy brief</div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.caption("Evidence-led product exploration, from customer voice to concept.")


st.markdown(
    """
    <section class="hero">
      <div class="hero-tag">CUSTOMER-LED PRODUCT INTELLIGENCE</div>
      <h1>Find the opportunity hidden in customer feedback.</h1>
      <p>Turn review evidence into recurring product flaws, measurable engineering
      concepts, and a strategy brief your team can act on.</p>
    </section>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="eyebrow">New analysis</div>', unsafe_allow_html=True)
st.markdown('<h2 class="workspace-title">Set up your research</h2>', unsafe_allow_html=True)
st.markdown(
    '<p class="workspace-copy">Choose a product category and, optionally, a review dataset to get started.</p>',
    unsafe_allow_html=True,
)

with st.form("analysis_form"):
    category = st.text_input(
        "Product category",
        placeholder="e.g. Green Tea",
        help="A specific category helps focus review analysis and competitor research.",
    )

    submitted = st.form_submit_button(
        "Generate product analysis  →",
        type="primary",
        use_container_width=True,
    )

if submitted:
    if not category.strip():
        st.warning("Enter a product category to start the analysis.")
    else:
        initial_state = {
            "category": category.strip(),
            "logs": [],
        }
        final = dict(initial_state)

        labels = {
            "review_scraper": "Collecting review evidence",
            "flaw_finder": "Analyzing recurring customer flaws",
            "competitor_research": "Researching competitor specifications",
            "spec_drafter": "Drafting engineering opportunities",
            "spec_critic": "Reviewing engineering specifications",
            "brief_generator": "Preparing the strategy brief",
        }

        try:
            with st.status("Building your product intelligence report…", expanded=True) as status:
                for update in graph.stream(initial_state, stream_mode="updates"):
                    for node, output in update.items():
                        final.update(output)
                        st.write(f" {labels.get(node, node)}")
                status.update(label="Analysis complete", state="complete")
            st.session_state["trendrecon_result"] = final
        except Exception as exc:
            st.error("The analysis could not be completed.")
            st.exception(exc)

result = st.session_state.get("trendrecon_result")

if result:
    st.markdown("---")
    st.markdown('<div class="eyebrow">Analysis report</div>', unsafe_allow_html=True)
    st.markdown(f"## {escape(result['category'])}")
    st.markdown(
        f'<span class="source-pill">Evidence source · '
        f'{escape(result.get("review_source", "unknown"))}</span>',
        unsafe_allow_html=True,
    )
    st.write("")

    metric1, metric2, metric3 = st.columns(3)
    metric1.metric("Reviews analyzed", result.get("review_count", 0))
    metric2.metric("Customer flaws", len(result.get("flaws", [])))
    metric3.metric("Engineering specs", len(result["spec_draft"].specs))

    brief_tab, flaws_tab, specs_tab, activity_tab = st.tabs(
        ["Strategy brief", "Customer voice", "Engineering specs", "Activity"]
    )

    with brief_tab:
        st.markdown(result["final_brief"])
        st.download_button(
            "Download strategy brief",
            data=result["final_brief"],
            file_name="product_strategy_brief.md",
            mime="text/markdown",
        )

    with flaws_tab:
        st.markdown("### What customers are experiencing")
        st.caption("Recurring product issues identified in the available review sample.")
        for index, flaw in enumerate(result["flaws"], start=1):
            with st.container(border=True):
                left, right = st.columns([5, 1])
                with left:
                    st.markdown(f"#### {index:02d} · {flaw.title}")
                    st.write(flaw.description)
                with right:
                    st.metric("Severity", f"{flaw.severity}/5")
                st.caption(f"Estimated frequency · {flaw.frequency_estimate}")
                for quote in flaw.example_quotes:
                    st.markdown(f"> {quote}")

    with specs_tab:
        draft = result["spec_draft"]
        st.markdown("### From customer problem to product decision")
        st.caption(f"Estimated cost impact · {draft.estimated_cost_impact}")
        st.dataframe(
            [
                {
                    "Component": item.component,
                    "Competitor baseline": item.competitor_baseline,
                    "Proposed specification": item.proposed_spec,
                    "Flaw addressed": item.solves_flaw,
                    "Rationale": item.rationale,
                }
                for item in draft.specs
            ],
            use_container_width=True,
            hide_index=True,
        )

    with activity_tab:
        st.markdown("### Analysis activity")
        for line in result.get("logs", []):
            st.write(f" {line}")
