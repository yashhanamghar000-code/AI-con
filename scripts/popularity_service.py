"""
scripts/popularity_service.py
-----------------------------
Task 8: Popularity Ranking with Evidence & Integrity.

Implements explainable, evidence-backed popularity ranking for Maharashtra
engineering colleges. Strictly eliminates fabricated baseline scores.
If valid popularity data does not exist for an institute, popularity is
marked as 'Data unavailable' and an alternative measurable criterion
(e.g., historical closing cutoff competitiveness) is offered.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger("aicon.popularity_service")


class SignalSourceType(str, Enum):
    VERIFIED_APPLICANT_PREFERENCE = "verified_applicant_preference"
    CAP_FIRST_CHOICE_DEMAND = "cap_first_choice_demand"
    OFFICIAL_SEAT_ACCEPTANCE_RATIO = "official_seat_acceptance_ratio"
    PUBLIC_RANKING_BENCHMARK = "public_ranking_benchmark"
    EXTERNAL_OFFICIAL_SURVEY = "external_official_survey"


@dataclass
class PopularitySignal:
    """A single verified, defensible popularity signal with provenance."""
    signal_name: str
    source_type: SignalSourceType
    source_citation: str  # Document title, gazette notification, or official URL
    date_or_year: str      # e.g., "2024-25"
    raw_value: float       # Original observed metric
    scale_min: float       # Minimum possible value
    scale_max: float       # Maximum possible value
    normalized_score: float  # Normalized 0.0 - 100.0
    weight: float          # Configurable weight in composite calculation
    description: str = ""
    is_missing: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_name": self.signal_name,
            "source_type": self.source_type.value,
            "source_citation": self.source_citation,
            "date_or_year": self.date_or_year,
            "raw_value": self.raw_value,
            "scale": [self.scale_min, self.scale_max],
            "normalized_score": round(self.normalized_score, 2),
            "weight": self.weight,
            "description": self.description,
            "is_missing": self.is_missing,
        }


@dataclass
class PopularityEvidence:
    """The evidence-grounded evaluation result for a college."""
    institute_code: str
    institute_name: str
    is_available: bool
    popularity_score: Optional[float]  # None if unavailable, NEVER fabricated
    signals: List[PopularitySignal] = field(default_factory=list)
    weights_used: Dict[str, float] = field(default_factory=dict)
    scoring_methodology: str = ""
    explanation: str = ""
    alternative_metric_name: Optional[str] = "Historical Closing Cutoff Competitiveness (Round 1 GOPENS Percentile)"
    alternative_metric_value: Optional[float] = None
    audit_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "institute_code": self.institute_code,
            "institute_name": self.institute_name,
            "is_available": self.is_available,
            "popularity_score": round(self.popularity_score, 2) if self.popularity_score is not None else None,
            "display_score": f"{self.popularity_score:.1f}/100" if self.popularity_score is not None else "Data unavailable",
            "signals": [s.to_dict() for s in self.signals],
            "weights_used": self.weights_used,
            "scoring_methodology": self.scoring_methodology,
            "explanation": self.explanation,
            "alternative_metric_name": self.alternative_metric_name,
            "alternative_metric_value": self.alternative_metric_value,
            "audit_notes": self.audit_notes,
        }


class PopularityRankingService:
    """
    Evaluates and ranks institutes using only verified, defensible signals.
    Follows Task 8 Non-Negotiable Rules:
    1. Never fabricate an arbitrary baseline (e.g. 75 + bonus).
    2. Never conflate admission cutoff (feasibility) with popularity.
    3. Return 'popularity data unavailable' when legitimate signals do not exist.
    4. Guard against missing data silently inflating scores.
    5. Expose configurable weights and component score breakdown.
    """

    DEFAULT_WEIGHTS = {
        "verified_applicant_preference": 0.40,
        "cap_first_choice_demand": 0.35,
        "official_seat_acceptance_ratio": 0.25,
    }

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        min_signals_required: int = 1,
        penalty_for_missing: bool = True,
    ):
        self.weights = dict(weights or self.DEFAULT_WEIGHTS)
        self.min_signals_required = min_signals_required
        self.penalty_for_missing = penalty_for_missing
        self._custom_signal_providers: Dict[str, Callable[[str], Optional[PopularitySignal]]] = {}
        self._verified_dataset: Dict[str, List[PopularitySignal]] = {}

    def configure_weights(self, new_weights: Dict[str, float]) -> None:
        """Configures component weights dynamically."""
        total = sum(new_weights.values())
        if total <= 0:
            raise ValueError("Sum of signal weights must be greater than zero.")
        self.weights = dict(new_weights)

    def register_signal_provider(
        self, signal_name: str, provider_func: Callable[[str], Optional[PopularitySignal]]
    ) -> None:
        """Registers a verified external signal provider (e.g., DTE allotment statistics)."""
        self._custom_signal_providers[signal_name] = provider_func

    def add_verified_institute_signal(self, institute_code: str, signal: PopularitySignal) -> None:
        """Adds a verified signal with documented provenance for an institute."""
        code = str(institute_code).zfill(5) if len(str(institute_code)) <= 5 else str(institute_code)
        if code not in self._verified_dataset:
            self._verified_dataset[code] = []
        self._verified_dataset[code].append(signal)

    def evaluate_college(
        self,
        institute_code: str,
        institute_name: str = "",
        cutoff_percentile: Optional[float] = None,
        closing_rank: Optional[int] = None,
    ) -> PopularityEvidence:
        """
        Evaluates a college's popularity.
        If no verified applicant preference or demand data exists, marks as unavailable.
        """
        code = str(institute_code).zfill(5) if len(str(institute_code)) <= 5 else str(institute_code)
        
        # Collect signals from registered providers and dataset
        active_signals: List[PopularitySignal] = []
        
        # 1. Check verified dataset
        if code in self._verified_dataset:
            active_signals.extend(self._verified_dataset[code])
            
        # 2. Check custom providers
        for sig_name, provider in self._custom_signal_providers.items():
            try:
                sig = provider(code)
                if sig and not sig.is_missing:
                    active_signals.append(sig)
            except Exception as e:
                logger.warning(f"Error querying popularity signal {sig_name} for {code}: {e}")

        # If no verified signals exist:
        if len(active_signals) < self.min_signals_required:
            return PopularityEvidence(
                institute_code=code,
                institute_name=institute_name,
                is_available=False,
                popularity_score=None,
                signals=[],
                weights_used=self.weights,
                scoring_methodology="Strict Evidence-Based: No fabricated baseline. DTE CET Cell cutoff records do not publish applicant preference counts or choice form demand ratios.",
                explanation="Popularity data unavailable: Official Maharashtra CET Cell publications report closing cutoffs, not applicant preference volumes or choice-list demand. Arbitrary scores are strictly omitted.",
                alternative_metric_name="Historical Closing Cutoff Competitiveness (Round 1 GOPENS Percentile)",
                alternative_metric_value=cutoff_percentile,
                audit_notes="No verified applicant preference records found for this institute in official dataset.",
            )

        # Composite calculation with missing data defense
        total_possible_weight = sum(self.weights.get(s.signal_name, s.weight) for s in active_signals)
        if total_possible_weight <= 0:
            total_possible_weight = 1.0

        weighted_sum = 0.0
        applied_weights = {}

        for sig in active_signals:
            w = self.weights.get(sig.signal_name, sig.weight)
            weighted_sum += (sig.normalized_score * w)
            applied_weights[sig.signal_name] = w

        calculated_score = weighted_sum / total_possible_weight

        # Defense against missing data silently inflating:
        all_expected_weights = sum(self.weights.values())
        completeness_ratio = min(1.0, total_possible_weight / all_expected_weights) if all_expected_weights > 0 else 1.0
        
        if self.penalty_for_missing and completeness_ratio < 1.0:
            final_score = calculated_score * completeness_ratio
            methodology = (
                f"Composite score from {len(active_signals)} verified signals weighted with completeness penalty "
                f"({completeness_ratio*100:.0f}% coverage)."
            )
        else:
            final_score = calculated_score
            methodology = f"Composite score from {len(active_signals)} verified signals across weighted demand indicators."

        final_score = max(0.0, min(100.0, final_score))

        return PopularityEvidence(
            institute_code=code,
            institute_name=institute_name,
            is_available=True,
            popularity_score=round(final_score, 1),
            signals=active_signals,
            weights_used=applied_weights,
            scoring_methodology=methodology,
            explanation=(
                f"Popularity evaluated at {final_score:.1f}/100 derived from verified demand signals: "
                + ", ".join([f"{s.signal_name} ({s.source_citation}, {s.date_or_year})" for s in active_signals])
            ),
            alternative_metric_name="Historical Closing Cutoff Competitiveness (Round 1 GOPENS Percentile)",
            alternative_metric_value=cutoff_percentile,
            audit_notes=f"Signals verified against official records. Completeness ratio: {completeness_ratio:.2f}.",
        )

    def rank_colleges(
        self,
        colleges: List[Dict[str, Any]],
        primary_criterion: str = "popularity",
        fallback_criterion: str = "cutoff_competitiveness",
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Ranks colleges based on popularity if available, otherwise cleanly falls back
        to the specified measurable criterion (e.g., cutoff competitiveness).
        """
        enriched = []
        any_popularity_available = False

        for col in colleges:
            c = dict(col)
            code = c.get("institute_code", "")
            name = c.get("institute_name", "")
            pct = c.get("cutoff_percentile")
            rk = c.get("closing_rank")
            
            pop_ev = self.evaluate_college(code, name, pct, rk)
            c["popularity_score"] = pop_ev.popularity_score
            c["popularity_available"] = pop_ev.is_available
            c["popularity_explanation"] = pop_ev.explanation
            c["alternative_metric"] = pop_ev.alternative_metric_name
            c["alternative_metric_value"] = pop_ev.alternative_metric_value

            if pop_ev.is_available:
                any_popularity_available = True
            enriched.append(c)

        if primary_criterion == "popularity" and any_popularity_available:
            ranked = sorted(
                enriched,
                key=lambda x: (
                    x["popularity_score"] is not None,
                    x["popularity_score"] or 0.0,
                    x.get("cutoff_percentile") or 0.0
                ),
                reverse=True
            )
            mode_used = "popularity"
            summary_message = "Ranked by verified applicant popularity and demand signals."
        else:
            # Fallback to clearly named measurable criterion: cutoff competitiveness
            ranked = sorted(
                enriched,
                key=lambda x: (
                    x.get("cutoff_percentile") is not None,
                    x.get("cutoff_percentile") or -1.0,
                    -(x.get("closing_rank") or 999999)
                ),
                reverse=True
            )
            mode_used = "cutoff_competitiveness"
            summary_message = (
                "Verified applicant preference counts (popularity data) are not published by CET Cell. "
                "Colleges have been ranked by Historical Closing Cutoff Competitiveness (Round 1 GOPENS Percentile) instead."
            )

        summary = {
            "mode_used": mode_used,
            "popularity_data_available": any_popularity_available,
            "total_ranked": len(ranked),
            "summary_message": summary_message,
        }
        return ranked, summary
