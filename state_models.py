from typing import TypedDict, List, Optional
from pydantic import BaseModel, Field


# ---------- Structured LLM outputs ----------
class Flaw(BaseModel):
    title: str = Field(description="Short name of the structural issue, e.g. 'Armrest breakage'")
    description: str = Field(description="What fails and why buyers are upset")
    frequency_estimate: str = Field(description="How common this is, e.g. 'Very common (~30% of reviews)'")
    example_quotes: List[str] = Field(description="2-3 short verbatim buyer quotes proving the flaw")
    severity: int = Field(ge=1, le=5, description="1 = minor annoyance, 5 = product failure")


class FlawReport(BaseModel):
    top_flaws: List[Flaw] = Field(description="The most important structural / physical complaints")


class SpecItem(BaseModel):
    component: str = Field(description="Part or subsystem, e.g. 'Armrest mounting bracket'")
    competitor_baseline: str = Field(description="What competitors typically ship today")
    proposed_spec: str = Field(description="Concrete engineering spec with materials, dimensions, tolerances, ratings")
    solves_flaw: str = Field(description="Title of the flaw this addresses")
    rationale: str = Field(description="Why this spec fixes the flaw")


class SpecDraft(BaseModel):
    specs: List[SpecItem]
    estimated_cost_impact: str = Field(description="Rough unit-cost delta vs. typical competitor")


class SpecCritique(BaseModel):
    approved: bool = Field(description="True only if every flaw is fully addressed with concrete, testable specs")
    issues: List[str] = Field(description="Problems: vague specs, unaddressed flaws, unrealistic claims")
    suggestions: List[str] = Field(description="Specific fixes for the drafter")


# ---------- LangGraph shared state ----------
class TrendReconState(TypedDict, total=False):
    # inputs
    category: str
    dataset_path: Optional[str]

    # scraper node
    reviews: List[str]
    review_source: str          # "csv" or "web"
    review_count: int

    # flaw finder node
    flaws: List[Flaw]

    # spec optimization loop
    competitor_context: str
    spec_draft: Optional[SpecDraft]
    critique: Optional[SpecCritique]
    iteration: int

    # final output
    final_brief: str
    logs: List[str]