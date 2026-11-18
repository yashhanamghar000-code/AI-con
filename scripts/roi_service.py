"""
ROI Service (Task 9)
-------------------
Provides explainable, verified Return on Investment (ROI) evaluations
grounded strictly in sourced fee structures and placement statistics.

Rules & Anti-Hallucination Contracts (Task 9):
1. Never invent arbitrary "Tier 1", "Tier 2", "Moderate", or "High" ROI tiers.
2. If either fee or placement data is missing, mark ROI as 'not_computable'.
3. Never calculate ROI from an annual fee without normalizing across the full
   degree time horizon (e.g. 4 years for B.E./B.Tech) and explaining the formula.
4. Clearly distinguish median package from average package, and branch-level from
   institute-level figures.
5. Clearly label the package-to-total-tuition ratio as a decision-support PROXY,
   not an actual financial internal rate of return (IRR).
6. Record full provenance: source citations, academic/placement years, verification status,
   and explicit analytical limitations.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class FeeData:
    amount: float
    currency: str = "INR"
    period: str = "annual"  # "annual", "total_course", "per_semester"
    fee_type: str = "tuition_fee"  # "tuition_fee", "total_fee", "interim_fee"
    course_duration_years: int = 4
    academic_year: str = "2024-25"
    source_citation: str = "Official Fee Regulating Authority (FRA) / College Fee Disclosure"
    verification_status: str = "unverified"  # "verified_official", "institute_disclosure", "unverified"

    def get_total_comparable_fee(self) -> float:
        """Normalize fee to total 4-year degree cost to prevent annual-vs-total mismatches."""
        if self.period == "total_course":
            return float(self.amount)
        elif self.period == "per_semester":
            return float(self.amount) * (self.course_duration_years * 2)
        elif self.period == "annual":
            return float(self.amount) * self.course_duration_years
        else:
            # Default assumption for engineering degree is 4 annual payments
            return float(self.amount) * self.course_duration_years


@dataclass
class PlacementData:
    amount: float  # In INR per annum
    metric_type: str = "median"  # "median" or "average"
    currency: str = "INR"
    scope: str = "institute_level"  # "branch_level" or "institute_level"
    branch_name: Optional[str] = None
    placement_year: str = "2023-24"
    source_citation: str = "NIRF / Official Placement Report"
    verification_status: str = "unverified"  # "verified_official", "nirf_disclosure", "unverified"


@dataclass
class ROIEvaluation:
    is_computable: bool
    status: str  # "computable" | "not_computable"
    ratio_proxy: Optional[float] = None
    ratio_display: Optional[str] = None
    formula_description: str = ""
    metric_label: str = "Package-to-Total-Tuition Proxy Ratio"
    fee_data: Optional[FeeData] = None
    placement_data: Optional[PlacementData] = None
    limitations: List[str] = field(default_factory=list)
    display_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_computable": self.is_computable,
            "status": self.status,
            "ratio_proxy": self.ratio_proxy,
            "ratio_display": self.ratio_display,
            "formula_description": self.formula_description,
            "metric_label": self.metric_label,
            "limitations": self.limitations,
            "display_summary": self.display_summary,
            "fee_source": self.fee_data.source_citation if self.fee_data else None,
            "placement_source": self.placement_data.source_citation if self.placement_data else None,
            "placement_metric": self.placement_data.metric_type if self.placement_data else None,
            "placement_scope": self.placement_data.scope if self.placement_data else None,
        }


class ROIService:
    """Service to evaluate and rank colleges by transparent, verified ROI metrics."""

    def __init__(self):
        pass

    def compute_roi(
        self,
        fee: Optional[FeeData],
        placement: Optional[PlacementData],
    ) -> ROIEvaluation:
        """Compute ROI proxy ratio with strict validation and limitation disclosures."""
        # 1. Missing data check
        if fee is None or placement is None:
            missing_parts = []
            if fee is None:
                missing_parts.append("fee data (tuition structure)")
            if placement is None:
                missing_parts.append("placement statistics (median/average package)")

            return ROIEvaluation(
                is_computable=False,
                status="not_computable",
                ratio_proxy=None,
                ratio_display=None,
                formula_description="ROI requires both verified total tuition and audited placement package.",
                metric_label="ROI Not Computable",
                fee_data=fee,
                placement_data=placement,
                limitations=[
                    f"Missing: {', '.join(missing_parts)}.",
                    "Official CET Cell CAP cutoff publications do not report fee or placement statistics.",
                    "Arbitrary or synthetic ROI tiers are strictly withheld to prevent misinformation.",
                ],
                display_summary=f"Not computable (Missing {', '.join(missing_parts)})",
            )

        # 2. Outlier and sanity validation
        if fee.amount <= 0 or placement.amount <= 0:
            return ROIEvaluation(
                is_computable=False,
                status="not_computable",
                ratio_proxy=None,
                ratio_display=None,
                formula_description="Invalid non-positive fee or placement amount.",
                metric_label="ROI Not Computable (Data Outlier)",
                fee_data=fee,
                placement_data=placement,
                limitations=["Fee or placement package amount is zero or negative."],
                display_summary="Not computable (Invalid non-positive numerical values)",
            )

        # 3. Calculate 4-year comparable tuition
        total_tuition = fee.get_total_comparable_fee()
        if total_tuition <= 0:
            return ROIEvaluation(
                is_computable=False,
                status="not_computable",
                ratio_proxy=None,
                ratio_display=None,
                formula_description="Normalized total tuition resulted in zero.",
                metric_label="ROI Not Computable",
                fee_data=fee,
                placement_data=placement,
                limitations=["Normalized tuition is zero."],
                display_summary="Not computable (Zero normalized tuition)",
            )

        # 4. Compute proxy ratio
        # Ratio = Annual Package (CTC) / Total 4-Year Tuition Cost
        annual_package = placement.amount
        proxy_ratio = round(annual_package / total_tuition, 2)

        # 5. Build formula explanation and limitations
        scope_str = "branch-specific" if placement.scope == "branch_level" else "institute-level"
        metric_str = "median" if placement.metric_type == "median" else "average"
        
        formula = (
            f"Ratio Proxy = (Annual {metric_str.capitalize()} Package [₹{annual_package:,.0f}]) / "
            f"(Total 4-Year Tuition [₹{total_tuition:,.0f} calculated from {fee.period} fee ₹{fee.amount:,.0f} × {fee.course_duration_years} yrs])"
        )

        limitations = [
            f"Proxy Metric: Compares 1-year gross placement package to 4-year tuition. This is a heuristic proxy, not a financial internal rate of return (IRR).",
            f"Placement Scope: Data is {scope_str} ({placement.placement_year}).",
            "Living Costs: Hostel, mess, and personal living expenses are excluded from fee calculations.",
            "Tax & Progression: Post-graduation career trajectory and taxes are not modeled.",
        ]

        if placement.metric_type == "average":
            limitations.append("Package metric is Average CTC, which may be skewed upward by high outlier packages. Median CTC is preferred when available.")

        if fee.verification_status != "verified_official":
            limitations.append(f"Fee verification status is '{fee.verification_status}' ({fee.source_citation}).")

        if placement.verification_status != "verified_official" and placement.verification_status != "nirf_disclosure":
            limitations.append(f"Placement verification status is '{placement.verification_status}' ({placement.source_citation}).")

        display_summary = f"{proxy_ratio:.2f}x ({metric_str.capitalize()} Pkg / 4-Yr Tuition)"

        return ROIEvaluation(
            is_computable=True,
            status="computable",
            ratio_proxy=proxy_ratio,
            ratio_display=f"{proxy_ratio:.2f}x",
            formula_description=formula,
            metric_label=f"Package-to-Tuition Ratio Proxy ({metric_str.capitalize()})",
            fee_data=fee,
            placement_data=placement,
            limitations=limitations,
            display_summary=display_summary,
        )

    def evaluate_college(
        self,
        college_data: Dict[str, Any],
        branch_name: Optional[str] = None,
    ) -> ROIEvaluation:
        """Evaluate ROI for a college dictionary from available structured facts."""
        fee_data: Optional[FeeData] = None
        placement_data: Optional[PlacementData] = None

        # Inspect if college_data has structured fee records
        raw_fee = college_data.get("fee_data") or college_data.get("annual_tuition_fee") or college_data.get("total_fees")
        if isinstance(raw_fee, dict):
            try:
                amt = float(raw_fee.get("amount", 0))
                if amt > 0:
                    fee_data = FeeData(
                        amount=amt,
                        currency=raw_fee.get("currency", "INR"),
                        period=raw_fee.get("period", "annual"),
                        fee_type=raw_fee.get("fee_type", "tuition_fee"),
                        course_duration_years=int(raw_fee.get("course_duration_years", 4)),
                        academic_year=str(raw_fee.get("academic_year", "2024-25")),
                        source_citation=str(raw_fee.get("source_citation", "Official Fee Disclosure")),
                        verification_status=str(raw_fee.get("verification_status", "unverified")),
                    )
            except (ValueError, TypeError):
                pass
        elif isinstance(raw_fee, (int, float)) and raw_fee > 0:
            fee_data = FeeData(
                amount=float(raw_fee),
                period="annual",
                source_citation="Extracted College Profile",
                verification_status="unverified",
            )

        # Inspect if college_data has structured placement records
        raw_placement = college_data.get("placement_data") or college_data.get("placement_mentions")
        if isinstance(raw_placement, dict):
            try:
                amt = float(raw_placement.get("amount", 0))
                if amt > 0:
                    placement_data = PlacementData(
                        amount=amt,
                        metric_type=raw_placement.get("metric_type", "median"),
                        currency=raw_placement.get("currency", "INR"),
                        scope=raw_placement.get("scope", "institute_level"),
                        branch_name=raw_placement.get("branch_name"),
                        placement_year=str(raw_placement.get("placement_year", "2023-24")),
                        source_citation=str(raw_placement.get("source_citation", "Official Placement Report")),
                        verification_status=str(raw_placement.get("verification_status", "unverified")),
                    )
            except (ValueError, TypeError):
                pass
        elif isinstance(raw_placement, (int, float)) and raw_placement > 0:
            placement_data = PlacementData(
                amount=float(raw_placement),
                metric_type="average",
                source_citation="Extracted College Profile",
                verification_status="unverified",
            )

        return self.compute_roi(fee_data, placement_data)

    def rank_by_roi(
        self,
        colleges: List[Dict[str, Any]],
        branch_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Rank colleges by ROI where computable, and transparently segregate uncomputable colleges."""
        computable = []
        not_computable = []

        for c in colleges:
            eval_res = self.evaluate_college(c, branch_name=branch_name)
            item = dict(c)
            item["roi_evaluation"] = eval_res.to_dict()
            item["roi_computable"] = eval_res.is_computable
            item["roi_ratio"] = eval_res.ratio_proxy
            item["roi_summary"] = eval_res.display_summary

            if eval_res.is_computable:
                computable.append(item)
            else:
                not_computable.append(item)

        # Sort computable colleges descending by proxy ratio
        computable.sort(key=lambda x: x["roi_ratio"] or 0.0, reverse=True)

        return {
            "computable_count": len(computable),
            "not_computable_count": len(not_computable),
            "ranked_colleges": computable,
            "unranked_colleges": not_computable,
            "total_count": len(colleges),
        }
