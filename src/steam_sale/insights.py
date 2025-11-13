from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from src.steam_sale.logging_setup import logger
from src.steam_sale.config import settings

import requests

try:
    from openai import OpenAI
except Exception:
    OpenAI = None # OpenAI is optional and may not be installed


class NewsClient:
    """
    A small wrapper around NewsAPI to fetch news articles about a game.
    """

    def __init__(self, api_key:str | None, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _is_relevant_article(self, title: str, game_name: str) -> bool:
        """
        Very small heuristic filter to keep only relevant headlines.

        Rules:
        - If title contains the game name (case-insensitive), good.
        - Or if title mentions sale/discount/deal/bundle/promo, we consider it.       
        """

        if not title:
            return False
        
        title_lower = title.lower()
        game_lower = (game_name or "").lower().strip()

        # if the game is known, checking if it's in the title
        if game_lower and game_lower in title_lower:
            return True
        
        # checking for sale/discount keywords
        sale_keywords = [
            "steam sale",
            "sale",
            "discount",
            "deal",
            "bundle",
            "promo",
            "promotion",
            "off",
            "% off",
            "price cut",
            "price drop",
            "clearance",
            "flash sale",
            "limited time",
            "special offer",
            "holiday sale",
            "black friday",
        ]

        if any(word in title_lower for word in sale_keywords):
            return True
        
        return False

    def is_enabled(self) -> bool:
        """Check if the NewsAPI client is properly configured."""

        if self.api_key:
            return True
        return False
    
    def fetch_game_news(self, game_name: str, limit: int = 3) -> list[dict]:
        """
        Fetches up to a limit recent articles abobut this game + any discount or sales.
        Returns a list of relevant articles with title, source and url.
        If anything fails, returns an empty list.
        """

        if not self.is_enabled():
            return []
        
        # building a query: game name + sale/discount hints
        query = f"{game_name} Steam sale OR discount OR deal"

        params = {
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": limit,
        }

        headers = {"X-Api-Key": self.api_key}

        try:
            url = f"{self.base_url}/everything"
            resp = requests.get(url, params=params, headers=headers, timeout=3.0)
            if resp.status_code != 200:
                msg = resp.text[:200].replace("\n", " ")
                logger.warning(
                    "newsapi_fetch_failed_non_200",
                    extra={
                        "status_code": resp.status_code,
                        "body_snippet": msg,
                    },
                )
                return []
            
            data = resp.json()
            articles = data.get("articles", [])

            results: list[dict] = []

            for article in articles[:limit]:
                title = article.get("title")
                source = (article.get("source") or {}).get("name")
                url = article.get("url")

                if not title:
                    continue

                # running relevance filter
                if not self._is_relevant_article(title=title, game_name=game_name):
                    continue

                item = {
                    "title": title,
                    "source": source,
                    "url": url,
                }
                results.append(item)

            return results
        
        except Exception as e:
            logger.warning(
                "newsapi_fetch_failed_exception",
                extra={"error": str(e)},
            )
            return []


@dataclass
class InsightService:
    """
    This class is responsible for turning raw prediction results -> output + metadata
    into human friendly "insights" block.
    """

    openai_enabled: bool = False
    _openai_client: Any | None = None
    _openai_model: str | None = None
    news_client: NewsClient | None = None

    def __post_init__(self):
        """
        Post-initialization to set up OpenAI client if enabled.
        """

        api_key = settings.OPENAI_API_KEY
        model = settings.OPENAI_MODEL

        if api_key and model and OpenAI is not None:
            try:
                # creating OpenAI client instance
                self._openai_client = OpenAI(api_key=api_key)
                self._openai_model = model
                self.openai_enabled = True
                logger.info("insights_openai_enabled", extra={"error": model})
            except Exception as e:
                logger.warning("insights_openai_init_falied", extra={"error": str(e)})
        else:
            self.openai_enabled = False

        news_api_key = settings.NEWS_API_KEY
        news_base_url = settings.NEWS_API_BASE_URL
        self.news_client = NewsClient(api_key=news_api_key, base_url=news_base_url)

        if self.news_client.is_enabled():
            logger.info(
                "newsapi_enabled",
                extra={"base_url": news_base_url},
            )
        else:
            logger.info("newsapi_disabled")

    def build_insights(self, appid: int, prediction: Dict[str, Any],
                       features: Dict[str, Any], game_name: Optional[str] = None) -> Dict[str, Any]:
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
        contextual_factors: List[str] = self._extract_contextual_factors(features)

        # fetching related game news
        news: List[Dict[str, Any]] = []
        if game_name and self.news_client and self.news_client.is_enabled():
            logger.info(
                "newsapi_fetch_start",
                extra={"appid": appid, "game_name": game_name},
            )
            news = self.news_client.fetch_game_news(game_name, limit=3)
            logger.info(
                "newsapi_fetch_done",
                extra={"appid": appid, "game_name": game_name, "count": len(news)},
            )

        # openai generated summary (if enabled)
        openai_summary: Optional[str] = None
        if self.openai_enabled:
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
    
    def build_combined_insights(
    self,
    appid: int,
    game_name: str,
    pred_30: Dict[str, Any],
    pred_60: Dict[str, Any],
    features: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Unified insights builder for cases where we have BOTH 30d and 60d predictions.

        This is what we should use for:
        - title search (live lookup)
        - precomputed upcoming games

        Returns a consistent structure:
        {
        "score_30d": float,
        "score_60d": float,
        "will_discount_30d": bool,
        "will_discount_60d": bool,
        "contextual_factors": [...],
        "news": [...],
        "bullets": ["...", "...", "..."],  # 3 concise recommendation bullets
        }
        """

        score_30 = float(pred_30.get("score", 0.0))
        score_60 = float(pred_60.get("score", 0.0))
        will_30 = bool(pred_30.get("will_discount", False))
        will_60 = bool(pred_60.get("will_discount", False))

        # re-use your existing factor extractor
        contextual_factors = self._extract_contextual_factors(features)

        # shared NewsAPI usage
        news: List[Dict[str, Any]] = []
        if self.news_client and self.news_client.is_enabled():
            try:
                logger.info(
                    "newsapi_fetch_start",
                    extra={"appid": appid, "game_name": game_name},
                )
                news = self.news_client.fetch_game_news(game_name, limit=3)
                logger.info(
                    "newsapi_fetch_done",
                    extra={"appid": appid, "game_name": game_name, "count": len(news)},
                )
            except Exception as e:
                logger.warning(
                    "newsapi_fetch_failed_combined",
                    extra={"appid": appid, "game_name": game_name, "error": str(e)},
                )
                news = []

        # Build 3 bullets either via OpenAI or deterministic fallback
        bullets: List[str] = []
        if self.openai_enabled:
            try:
                bullets = self._build_openai_summary_combined(
                    appid=appid,
                    game_name=game_name,
                    score_30=score_30,
                    score_60=score_60,
                    contextual_factors=contextual_factors,
                    news=news,
                )
            except Exception as e:
                logger.warning(
                    "insights_openai_failed_combined",
                    extra={"appid": appid, "error": str(e)},
                )
                bullets = []

        if not bullets:
            bullets = self._fallback_combined_bullets(
                score_30=score_30,
                score_60=score_60,
                will_30=will_30,
                will_60=will_60,
            )

        return {
            "score_30d": score_30,
            "score_60d": score_60,
            "will_discount_30d": will_30,
            "will_discount_60d": will_60,
            "contextual_factors": contextual_factors,
            "news": news,
            "bullets": bullets,
        }
    
    def _fallback_combined_bullets(
    self,
    score_30: float,
    score_60: float,
    will_30: bool,
    will_60: bool,
    ) -> List[str]:
        """
        Fallback: 3 concise bullets based purely on the two probabilities.
        No fluff, no promises.
        """

        p30 = score_30 * 100
        p60 = score_60 * 100
        bullets: List[str] = []

        # Bullet 1: 30-day view
        if p30 < 20:
            bullets.append("Low chance of a discount in the next 30 days.")
        elif p30 > 60:
            bullets.append("Strong chance of a discount within the next 30 days.")
        else:
            bullets.append("Some chance of a discount in the next 30 days, but not high-confidence.")

        # Bullet 2: 60-day view
        if p60 < 30:
            bullets.append("Even over 60 days, a meaningful discount looks unlikely.")
        elif p60 > 60:
            bullets.append("Within 60 days, a discount becomes quite plausible based on similar titles.")
        else:
            bullets.append("Over 60 days, odds improve somewhat but remain uncertain.")

        # Bullet 3: actionable recommendation
        if will_30 or will_60:
            bullets.append(
                "If you’re price-sensitive and can wait, holding off may be reasonable; otherwise buying near launch is still defensible."
            )
        else:
            bullets.append(
                "If you want to play soon, buying at or near launch is reasonable; waiting solely for a big discount may not pay off quickly."
            )

        # Ensure exactly 3
        return bullets[:3]
    
    def _build_openai_summary_combined(
        self,
        appid: int,
        game_name: str,
        score_30: float,
        score_60: float,
        contextual_factors: List[str],
        news: List[Dict[str, Any]],
    ) -> List[str]:
        """
        OpenAI-backed generator for EXACTLY 3 short bullets for combined 30d + 60d view.

        Returns [] on any failure; caller will fallback.
        """

        if not self._openai_client or not self._openai_model:
            return []

        p30 = f"{score_30 * 100:.1f}%"
        p60 = f"{score_60 * 100:.1f}%"

        factors_text = (
            "\n".join(f"- {f}" for f in contextual_factors[:4])
            if contextual_factors
            else "- (no major additional signals detected)"
        )

        news_text = ""
        if news:
            news_lines = []
            for item in news[:3]:
                title = item.get("title", "")
                source = item.get("source", "")
                if not title:
                    continue
                if source:
                    news_lines.append(f"- {title} ({source})")
                else:
                    news_lines.append(f"- {title}")
            if news_lines:
                news_text = "Recent mentions:\n" + "\n".join(news_lines)

        prompt = f"""
You are assisting users of a Steam discount forecast tool.

Game: {game_name}
Model estimates:
- Next 30 days discount probability: {p30}
- Next 60 days discount probability: {p60}

Contextual signals:
{factors_text}

{news_text}

Write EXACTLY 3 concise bullet points:
- Summarise likelihood of discount in 30d and 60d.
- Give a clear, pragmatic recommendation (e.g. lean buy now vs lean wait).
- Be cautious: no guarantees, no hype.
- Total response under 70 words.
- Output ONLY the 3 bullets, each on its own line, no numbering or extra text.
"""

        response = self._openai_client.responses.create(
            model=self._openai_model,
            input=prompt,
            max_output_tokens=160,
        )

        try:
            raw = response.output[0].content[0].text
        except Exception:
            return []

        lines = [
            line.strip("•*- ").strip()
            for line in (raw or "").splitlines()
            if line.strip()
        ]
        bullets = [ln for ln in lines if ln][:3]
        return bullets
    
    def _make_confidence_comment(self, score: float, horizon: str, will_discount: bool) -> str:
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
    
    def _extract_contextual_factors(self, features: Dict[str, Any]) -> List[str]:
        """
        Build simple, human-readable bullet points based on feature values.

        This version assumes the tool is mainly used for upcoming or newly
        released titles. The messages are about early discount behavior
        (launch window), not long-term catalog behavior.
        """
        factors: List[str] = []

        # 1) New / upcoming title hint (based on release_year)
        release_year = features.get("release_year")
        if release_year is not None:
            try:
                year_int = int(release_year)
                # You can tune this to the current year; keeping it generic here.
                if year_int >= 2024:
                    factors.append(
                        "This is a new or upcoming title; deep discounts right at or shortly after release are less common."
                    )
            except (TypeError, ValueError):
                # If parsing fails, we just skip this hint.
                pass

        # 2) Publisher size (using your one-hot bins if present)
        # These give us a feel for pricing behavior at launch.
        try:
            if features.get("publisher_size_bin__Major (>50)") == 1:
                factors.append(
                    "Published by a major publisher; they rarely offer big launch discounts, "
                    "but frequently participate in major Steam sale events."
                )
            elif features.get("publisher_size_bin__Large (16–50)") == 1:
                factors.append(
                    "Published by a large publisher; launch discounts are possible but usually modest."
                )
            elif features.get("publisher_size_bin__Medium (6–15)") == 1:
                factors.append(
                    "Published by a mid-sized publisher; they sometimes use launch-window promos to boost visibility."
                )
            elif features.get("publisher_size_bin__Small (≤5)") == 1:
                factors.append(
                    "Published by a smaller publisher; they may be more flexible with early discounts to attract players."
                )
        except Exception:
            # Any weirdness with types, we just skip publisher hints.
            pass

        # 3) Early Access flag
        early_access = features.get("early_access")
        if early_access is not None:
            try:
                if int(early_access) == 1:
                    factors.append(
                        "Launching in Early Access; pricing and discounts can be more experimental early on."
                    )
            except (TypeError, ValueError):
                pass

        # 4) Franchise activity: more previous titles -> more bundle/promo options
        franchise_count_prev = features.get("franchise_count_prev")
        if franchise_count_prev is not None:
            try:
                fcount = int(franchise_count_prev)
                if fcount >= 3:
                    factors.append(
                        "Part of an established franchise; launch or early bundles and promo discounts are more common."
                    )
            except (TypeError, ValueError):
                pass

        # 5) Proximity to major Steam sale windows
        # If the release timing aligns with a big sale, mention it as a factor.
        try:
            near_major_sale = False

            if int(features.get("is_summer_sale_window", 0)) == 1:
                near_major_sale = True
            if int(features.get("is_autumn_sale_window", 0)) == 1:
                near_major_sale = True
            if int(features.get("is_holiday_season", 0)) == 1:
                near_major_sale = True
            if int(features.get("within_7d_of_steam_sale", 0)) == 1:
                near_major_sale = True

            if near_major_sale:
                factors.append(
                    "Release is close to a major Steam sale window, which can increase the chance of early promotional pricing."
                )
        except (TypeError, ValueError):
            # If any of these flags are weird, we just ignore this block.
            pass

        return factors
    
    def _build_openai_summary(self, appid: int, score: float, horizon: str,
                              will_discount: bool, contextual_factors: List[str],
                              news: List[Dict[str, Any]]) -> str:
        """
        This function calls OpenAI to generate a short, user-friendly summary.

        It takes the model output, contextual factors, and any relevant news to produce
        a concise explanation suitable for end-users.
        """

        if not self._openai_client or not self._openai_model:
            raise RuntimeError("OpenAI client is not properly initialized.")
        
        lines: List[str] = []

        lines.append(f"Predicted probability of discount within {horizon}: {score:.2f}.")
        if will_discount:
            lines.append("The model suggests it is likely worth waiting for a discount.")
        else:
            lines.append("The model suggests a discount is unlikely in this window.")

        if contextual_factors:
            lines.append("Key factors:")
            for f in contextual_factors[:3]: # limiting to top 3 factors
                lines.append(f"- {f}")

        if news:
            lines.append("Recent news mentions:")
            for item in news[:3]:
                title = item.get("title", "")
                source = item.get("source", "")
                if title:
                    if source:
                        lines.append(f"- '{title}' from {source}")
                    else:
                        lines.append(f"- '{title}'")

        context_text = "\n".join(lines)

        prompt = (
            "You are a helpful assistant for a Steam sale prediction tool.\n"
            "Using the context below, write 1-2 short sentences to help a user decide "
            "whether to wait for a discount or buy now.\n"
            "Be factual, cautious, and do not promise anything.\n"
            "Context:\n"
            f"{context_text}\n"
            "Answer:"
        )

        # calling the OpenAI response/chat api via the official client
        # using a simple text style.
        response = self._openai_client.responses.create(
            model=self._openai_model,
            input=prompt,
            max_output_tokens=120,
        )

        try:
            output = response.output[0].content[0].text
            summary = output.strip()
        except Exception:
            summary = ""

        return summary

    
insight_service = InsightService(openai_enabled=True)