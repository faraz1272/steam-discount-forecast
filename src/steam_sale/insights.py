from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from src.steam_sale.logging_setup import logger

@dataclass
class InsightService:
    """
    This class is responsible for turning raw prediction results -> output + metadata
    into human friendly "insights" block.
    """

    openai_enabled: bool = False

    def build_insights(self, appid: int, prediction: Dict[str, Any],
                       features: Dict[str, Any]) -> Dict[str. Any]:
        """
        This fuction builds insights based on the prediction results and input features.

        Args:
            appid (int): Steam App ID of the game.
            prediction (Dict[str, Any]): Prediction results containing 'will_discount' and 'score'.
            features (Dict[str, Any]): Input features used for prediction.
        Returns:
            Dict[str, Any]: A dictionary containing insights about the prediction.
        """

        # extracting values from prediction dictionary
        score = float(prediction.get("score", 0.0))
        horizon = str(prediction.get("horizon", "30d"))
        will_discount = bool(prediction.get("will_discount", False))

        # builiding a simple and friendly comment about the prediction
        sale_confidence_comment = self._make_confidence_comment(score, horizon, will_discount)

        # adding a couple of contextual hints based on features
        contextual_factors = List[str] = self._extarct_contextual_factors(features)

        # placeholder for news/extertnal info. will populate later
        news: List[Dict[str, Any]] = []

        # openai generated summary (if enabled)
        openai_summary: Optional[str] = None
        if self.openai_enalbled:
            try:
                openai_summary = self._build_openai_summary(
                    appid=appid,
                    score=score,
                    horizon=horizon,
                    will_discount=will_discount,
                    contextual_factors=contextual_factors,
                    news=news,
                )
            except Exception as e:
                logger.warning(
                    "insights_openai_failed",
                    extra={"appid": appid, "error": str(e)},
                )
                openai_summary = None

        insights = {
            "sale_confidence_comment": sale_confidence_comment,
            "contextual_factors": contextual_factors,
            "news": news,
            "openai_summary": openai_summary,
        }

        return insights
    
    def _make_confidence_conmment(self, score: float, horizon: str, will_discount: bool) -> str:
        """
        This function creates a friendly comment based on the prediction score.
        """

        if score >= 0.85:
            return f"Very strong chance of a discount within the next {horizon}."
        if score >= 0.65:
            return f"Good chance of a discount within the next {horizon}."
        if score >= 0.45:
            if will_discount:
                return f"Borderline case, but slightly in favor of a discount within {horizon}."
            return f"Borderline probability; a discount within {horizon} is possible but uncertain."
        # score < 0.45
        return f"Unlikely to see a discount within the next {horizon} based on current signals."
    
    def _extarct_contextual_factors(self, features: Dict[str, Any]) -> List[str]:
        """ 
        This function extracts contextual factors from input features
        that may have influenced the prediction.
        """

        factors: List[str] = []

        # Example 1: release year hint
        release_year = features.get("release_year")
        if release_year is not None:
            try:
                year_int = int(release_year)
                if year_int >= 2024:
                    factors.append("Recently released title; early deep discounts are less common.")
                elif year_int <= 2018:
                    factors.append("Older title; more likely to appear in recurring sale events.")
            except (TypeError, ValueError):
                # If we can't parse, we simply skip this factor.
                pass

        # Example 2: publisher size
        publisher_size_log = features.get("publisher_size_log")
        if publisher_size_log is not None:
            try:
                size_val = float(publisher_size_log)
                if size_val >= 3.0:
                    factors.append("Published by a large publisher; they often join major seasonal sales.")
                elif size_val <= 1.5:
                    factors.append("Smaller publisher; discount patterns may be less predictable.")
            except (TypeError, ValueError):
                pass

        # Example 3: franchise activity
        franchise_count_prev = features.get("franchise_count_prev")
        if franchise_count_prev is not None:
            try:
                fcount = int(franchise_count_prev)
                if fcount >= 3:
                    factors.append("Part of an active franchise; bundles or franchise-wide discounts are common.")
            except (TypeError, ValueError):
                pass

        return factors
    
    def _build_openai_summary(self, appid: int, score: float, horizon: str,
                              will_discount: bool, contextual_factors: List[str],
                              news: List[Dict[str, Any]]) -> str:
        """
        Placeholder for future OpenAI integration.

        Here we would:
        - Construct a prompt using prediction + context + news
        - Call OpenAI's API
        - Return a short, clear summary string

        For now, we just return a static message so nothing breaks.
        """
        return (
            "AI summary is not enabled yet. "
            "Once connected, this will provide a short explanation using model signals and recent news."
        )
    
insight_service = InsightService()