from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict, List, Optional

from src.steam_sale.itad_client import itad_client
from src.steam_sale.feature_builder import feature_builder
from src.steam_sale.models.predictor import model_service
from src.steam_sale.insights import insight_service
from src.steam_sale.logging_setup import logger

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

SEED_PATH = os.path.join(
    BASE_DIR,
    "artifacts",
    "upcoming_seed.csv", 
)

OUTPUT_PATH = os.path.join(
    BASE_DIR,
    "artifacts",
    "upcoming_predictions.json",
)

def _parse_price(value: str | None) -> Optional[float]:
    if not value:
        return None
    v = value.strip().replace("$", "").replace("£", "").replace("€", "")
    try:
        return float(v)
    except ValueError:
        return None
    
def _pick_itad_candidate(name: str, results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    From a list of ITAD search results, pick the best matching candidate based on name similarity.
    If no match is found, returns the first result as a fallback.
    """

    if not results:
        return None
    
    name_lower = name.lower()

    for r in results:
        candidate_name = (r.get("name") or "").lower()
        if candidate_name == name_lower:
            return r
        
    return results[0]

def _extract_image_url_from_itad(game_info: dict, appid: int | None) -> str | None:
    # If ITAD info is missing or malformed, go straight to fallback
    if not isinstance(game_info, dict):
        if appid:
            return f"https://steamcdn-a.akamaihd.net/steam/apps/{appid}/header.jpg"
        return None

    assets = game_info.get("assets") or {}

    # Prefer bigger/better assets if present
    for key in ["boxart", "banner600", "banner400", "banner300", "banner145"]:
        url = assets.get(key)
        if isinstance(url, str) and url.strip():
            return url.strip()

    # Fallback: Steam header if appid looks valid
    if appid:
        return f"https://steamcdn-a.akamaihd.net/steam/apps/{appid}/header.jpg"

    return None

def build_upcoming_predictions() -> None:
    logger.info("upcoming_precompute_started", extra={"seed_path": SEED_PATH})

    # loading the prediction model
    model_service.load()

    if not os.path.exists(SEED_PATH):
        logger.error("upcoming_seed_file_missing", extra={"seed_path": SEED_PATH})
        raise FileNotFoundError(f"Seed file not found at {SEED_PATH}")
    
    records: List[Dict[str. Any]] = []

    with open(SEED_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for idx, row in enumerate(reader, start=1):
            name = (row.get("name") or "").strip()
            if not name:
                continue

            release_date = (row.get("release_date") or "").strip() or None
            price = _parse_price(row.get("price"))

            # trying to enrich through ITAD
            itad_info: Optional[Dict[str, Any]] = None
            itad_id: Optional[str] = None
            appid: int = 0

            if itad_client.is_enabled():
                logger.info("itad_enrich_attempt",
                            extra={"game_name": name})
                try:
                    search_result = itad_client.search_game(title=name, limit=5)
                    candidate = _pick_itad_candidate(name, search_result)

                    if candidate:
                        logger.info("itad_candidate_found",
                                    extra={"game_name": name, "itad_id": candidate.get("itad_id")})
                        itad_id = candidate.get("itad_id")
                        if itad_id:
                            logger.info("itad_fetch_info_attempt",
                                        extra={"game_name": name, "itad_id": itad_id})
                            itad_info = itad_client.get_game_info(itad_id)

                except Exception as e:
                    logger.warning(
                        "itad_enrich_failed",
                        extra={"game_name": name, "error": str(e)},
                    )

# ---- Decide final release_date and price (ITAD has priority) ----
            if itad_info:
                # ITAD release date if available
                itad_release = (
                    itad_info.get("releaseDate")
                    or itad_info.get("release_date")
                    or None
                )
                if itad_release:
                    release_date = itad_release  # override CSV

                # ITAD price if available 
                itad_price = itad_info.get("price")
                if isinstance(itad_price, (int, float)):
                    price = float(itad_price)

                # Steam appid from ITAD if present
                if itad_info.get("appid"):
                    appid = int(itad_info["appid"])
                else:
                    appid = 0
            else:
                # No ITAD info -> keep CSV values
                appid = 0

            # Safety fallback: if still no price, pick a neutral default
            if price is None:
                price = 39.99

            # ---- Build game payload for FeatureBuilder ----
            # This is what build_from_itad() will consume.
            game_payload: Dict[str, Any] = {}

            if itad_info:
                # start from ITAD info, but ensure the keys we care about are set
                game_payload = dict(itad_info)
                game_payload["releaseDate"] = release_date
                game_payload["price"] = price
                game_payload.setdefault("tags", itad_info.get("tags", []))
                if itad_id:
                    game_payload["id"] = itad_id
            else:
                # minimal payload built from our CSV + heuristics
                game_payload = {
                    "releaseDate": release_date,
                    "price": price,
                    "tags": [],
                }

            # building features
            try:
                features = feature_builder.build_from_itad(
                    appid=appid,
                    game=game_payload,
                )
            except Exception as e:
                logger.warning(
                    "feature_build_failed",
                    extra={"appid": appid, "game_name": name, "error": str(e)},
                )
                continue

            # making prediction for 30d horizon
            try:
                pred_30 = model_service.predict(
                    horizon="30d",
                    appid=appid,
                    features=features,
                    threshold=None,
                )

                pred_60 = model_service.predict(
                    horizon="60d",
                    appid=appid,
                    features=features,
                    threshold=None,
                )

            except Exception as e:
                logger.warning(
                    "upcoming_games_prediction_failed",
                    extra={"appid": appid, "game_name": name, "error": str(e)},
                )
                continue

            # generating combined insights for upcoming games
            try:
                insights = insight_service.build_combined_insights(
                    appid=appid,
                    game_name=name,
                    pred_30=pred_30,
                    pred_60=pred_60,
                    features=features,
                )
            except Exception as e:
                logger.warning(
                    "upcoming_games_insights_failed",
                    extra={"appid": appid, "game_name": name, "error": str(e)},
                )
                insights = None

            # image url 
            image_url = _extract_image_url_from_itad(itad_info, appid)

            record = {
                "appid": appid,
                "name": name,
                "release_date": release_date,
                "price": price,
                "image_url": image_url,
                # keep legacy top-levels mapped from 30d for now
                "horizon": "30d",
                "will_discount": pred_30["will_discount"],
                "score": pred_30["score"],
                "threshold": pred_30["threshold"],
                # explicit multi-horizon
                "score_30d": pred_30["score"],
                "will_discount_30d": pred_30["will_discount"],
                "threshold_30d": pred_30["threshold"],
                "score_60d": pred_60["score"],
                "will_discount_60d": pred_60["will_discount"],
                "threshold_60d": pred_60["threshold"],
                # unified insights (bullets + news)
                "insights": insights,
            }
            records.append(record)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    logger.info(
        "upcoming_precompute_done",
        extra={"count": len(records), "output_path": OUTPUT_PATH},
    )


if __name__ == "__main__":
    build_upcoming_predictions()