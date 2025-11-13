from datetime import datetime, date
from time import perf_counter
from typing import List, Dict, Any

import json
import os

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from src.steam_sale.config import settings
from src.steam_sale.exceptions import (
    SteamSaleError,
    ModelNotLoadedError,
    BadRequestError,
)
from src.steam_sale.feature_builder import feature_builder
from src.steam_sale.insights import insight_service
from src.steam_sale.itad_client import itad_client
from src.steam_sale.logging_setup import logger
from src.steam_sale.models.predictor import model_service
from src.steam_sale.schemas import (
    PredictRequest,
    PredictResponse,
    HealthResponse,
    UpcomingGame,
    GameSearchResult,
    PredictFromItadRequest,
    PredictFromItadResponse,
)

# -----------------------------------------------------------------------------
# FastAPI app
# -----------------------------------------------------------------------------

app = FastAPI(
    title=getattr(settings, "APP_NAME", "Steam Sale Prediction API"),
    default_response_class=JSONResponse,
)

# base dir: project root (steam-discount-forecast/)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))

# precomputed upcoming games file (from upcoming_precompute.py)
UPCOMING_FILE = os.path.join(BASE_DIR, "artifacts", "upcoming_predictions.json")

# Jinja2 templates
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates")
)

# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------


def _pick_itad_candidate(title: str, results: list[dict]) -> dict | None:
    """
    From a list of ITAD search results, pick the best matching candidate.
    If no exact match, return the first result as a fallback.
    """
    if not results:
        return None

    title_lower = title.lower().strip()

    for r in results:
        candidate_name = (r.get("name") or r.get("title") or "").lower().strip()
        if candidate_name == title_lower:
            return r

    return results[0]


def _parse_release_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except Exception:
        return None


def _extract_image_url_from_itad(game_info: dict | None, appid: int | None) -> str | None:
    """
    Prefer ITAD assets if present, otherwise fall back to Steam header.
    """
    if not isinstance(game_info, dict):
        if appid:
            return f"https://steamcdn-a.akamaihd.net/steam/apps/{appid}/header.jpg"
        return None

    assets = game_info.get("assets") or {}
    if isinstance(assets, dict):
        for key in ("boxart", "banner600", "banner400", "banner300", "banner145"):
            url = assets.get(key)
            if isinstance(url, str) and url.strip():
                return url.strip()

    if appid:
        return f"https://steamcdn-a.akamaihd.net/steam/apps/{appid}/header.jpg"

    return None


# -----------------------------------------------------------------------------
# Search + predict by title (ITAD + combined insights)
# -----------------------------------------------------------------------------


@app.get("/predict/search", response_model=GameSearchResult)
async def predict_by_title(
    title: str = Query(..., description="Game title to search via ITAD"),
):
    """
    Search a game by title via ITAD, build features, run 30d + 60d models,
    and return a combined insights object for the UI search card.
    """
    logger.info("predict_search_requested", extra={"title": title})

    if not itad_client.is_enabled():
        raise HTTPException(
            status_code=503,
            detail="ITAD integration is not configured on this deployment.",
        )

    # 1) Search ITAD
    try:
        search_results = itad_client.search_game(title=title, limit=5)
    except Exception as e:
        logger.error(
            "predict_search_itad_failed",
            extra={"title": title, "error": str(e)},
        )
        raise HTTPException(status_code=502, detail="Failed to query ITAD")

    if not search_results:
        raise HTTPException(
            status_code=404,
            detail=f"No ITAD match found for '{title}'. Try a different spelling.",
        )

    candidate = _pick_itad_candidate(title, search_results)
    if not candidate:
        raise HTTPException(status_code=404, detail="No suitable ITAD candidate found")

    itad_id = candidate.get("itad_id")
    if not itad_id:
        raise HTTPException(status_code=500, detail="Malformed ITAD search result")

    # 2) Detailed info from ITAD
    try:
        game_info = itad_client.get_game_info(itad_id)
    except Exception as e:
        logger.error(
            "predict_search_gameinfo_failed",
            extra={"title": title, "itad_id": itad_id, "error": str(e)},
        )
        raise HTTPException(status_code=502, detail="Failed to fetch ITAD game info")

    appid = int(game_info.get("appid") or 0)
    official_name = (
        game_info.get("title")
        or game_info.get("name")
        or candidate.get("title")
        or candidate.get("name")
        or title
    )
    release_raw = game_info.get("releaseDate") or game_info.get("release_date")
    release_dt = _parse_release_date(release_raw)
    launch_price = game_info.get("price") or None
    image_url = _extract_image_url_from_itad(game_info, appid)

    # NEW: live price via prices/v3
    price_amount, price_ccy, price_shop = itad_client.get_current_price_simple(
        itad_id=itad_id,
        country="US",   # or settings.ITAD_COUNTRY if you added one
    )

    # Use numeric amount for the UI; keep currency if you want to show it
    launch_price = price_amount  # float or None

    # 3) If already released -> no calibrated forecast, return info-style result
    if release_dt and release_dt < date.today():
        bullets = [
            "This game has already released.",
            "WaitForIt focuses on upcoming titles and launch-window discounts.",
            "Please check current store prices directly for real-time deals.",
        ]

        return GameSearchResult(
            appid=appid,
            name=official_name,
            release_date=release_raw,
            price=launch_price,
            image_url=image_url,
            score_30d=0.0,
            score_60d=0.0,
            will_discount_30d=False,
            will_discount_60d=False,
            insights={
                "score_30d": 0.0,
                "score_60d": 0.0,
                "will_discount_30d": False,
                "will_discount_60d": False,
                "contextual_factors": [],
                "news": [],
                "bullets": bullets,
            },
        )

    # 4) Build features from ITAD info
    try:
        features = feature_builder.build_from_itad(appid=appid, game=game_info)
    except Exception as e:
        logger.error(
            "predict_search_feature_build_failed",
            extra={"title": title, "appid": appid, "error": str(e)},
        )
        raise HTTPException(
            status_code=500,
            detail="Could not build features from ITAD data for this game.",
        )

    # 5) Run both horizons
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
        logger.error(
            "predict_search_model_failed",
            extra={"title": title, "appid": appid, "error": str(e)},
        )
        raise HTTPException(status_code=500, detail="Prediction failed for this title")

    # 6) Combined insights (3 bullets + news etc.)
    insights = insight_service.build_combined_insights(
        appid=appid,
        game_name=official_name,
        pred_30=pred_30,
        pred_60=pred_60,
        features=features,
    )

    # 7) Response for frontend search card
    return GameSearchResult(
        appid=appid,
        name=official_name,
        release_date=release_raw,
        price=launch_price,
        image_url=image_url,
        score_30d=pred_30["score"],
        score_60d=pred_60["score"],
        will_discount_30d=pred_30["will_discount"],
        will_discount_60d=pred_60["will_discount"],
        insights=insights,
    )

@app.get("/games/search")
async def suggest_games(title: str, limit: int = 8) -> List[Dict[str, Any]]:
    """
    Return minimal suggestions for the typeahead.
    Uses ITAD search and returns [{itad_id, title}] (plus appid/assets if available).
    """
    if not itad_client.is_enabled():
        raise HTTPException(status_code=503, detail="ITAD client not configured")

    try:
        # NOTE: use the plural method you have implemented on your client
        results = itad_client.search_game(title=title, limit=limit)  # <-- plural
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ITAD search failed: {e}")

    out: List[Dict[str, Any]] = []
    for r in results or []:
        out.append({
            "itad_id": r.get("id") or r.get("itad_id"),
            "title": r.get("title") or r.get("name"),
            # include appid/asset if present in your client response (optional):
            "appid": r.get("appid"),
            "assets": r.get("assets") or {},
        })
    return out

# -----------------------------------------------------------------------------
# Home: render dashboard with upcoming games
# -----------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """
    WaitForIt dashboard.
    Uses precomputed upcoming_predictions.json from upcoming_precompute.py.
    """
    try:
        with open(UPCOMING_FILE, "r", encoding="utf-8") as f:
            games = json.load(f)
    except Exception as e:
        logger.warning(
            "upcoming_file_load_failed",
            extra={"path": UPCOMING_FILE, "error": str(e)},
        )
        games = []

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "games": games,
            "app_name": "WaitForIt",
        },
    )


# -----------------------------------------------------------------------------
# Request logging middleware
# -----------------------------------------------------------------------------


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = perf_counter()
    response = await call_next(request)
    duration_ms = (perf_counter() - start_time) * 1000.0

    logger.info(
        "request_completed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
        },
    )

    return response


# -----------------------------------------------------------------------------
# Startup: load models
# -----------------------------------------------------------------------------


@app.on_event("startup")
async def startup_event():
    try:
        model_service.load()
        logger.info("startup_complete", extra={"env": settings.APP_ENV})
    except SteamSaleError as e:
        logger.exception("startup_failed", extra={"error": str(e)})


# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Checks if the models are loaded and the service is running."""
    loaded_30 = model_service.model_30d is not None
    loaded_60 = model_service.model_60d is not None

    status = "ok" if (loaded_30 and loaded_60) else "loading"

    return HealthResponse(
        status=status,
        model_30d_loaded=loaded_30,
        model_60d_loaded=loaded_60,
    )


# -----------------------------------------------------------------------------
# Core prediction endpoint (API-first, single horizon)
# -----------------------------------------------------------------------------


@app.post("/predict", response_model=PredictResponse)
async def predict(
    payload: PredictRequest,
    include_insights: bool = Query(
        False, description="If true, include single-horizon insights in response"
    ),
):
    """
    Main programmatic prediction endpoint.
    This is API-first; frontend uses /predict/search + precomputed upcoming instead.
    """
    try:
        result = model_service.predict(
            appid=payload.appid,
            horizon=payload.horizon,
            features=payload.features,
            threshold=payload.threshold,
        )

        if include_insights:
            insights = insight_service.build_insights(
                appid=payload.appid,
                prediction=result,
                features=payload.features,
                game_name=payload.game_name,
            )
            result["insights"] = insights

        return PredictResponse(**result)

    except BadRequestError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ModelNotLoadedError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except SteamSaleError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}",
        )
    except Exception:
        logger.exception("unhandled_error")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred",
        )


# -----------------------------------------------------------------------------
# Upcoming games API (backed by precomputed file)
# -----------------------------------------------------------------------------


@app.get("/games/upcoming", response_model=List[UpcomingGame])
async def get_upcoming_games():
    """
    Returns upcoming games with precomputed predictions + insights.
    Data is generated by upcoming_precompute.py into upcoming_predictions.json.
    """
    try:
        with open(UPCOMING_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise HTTPException(
            status_code=503,
            detail="Upcoming games data not generated yet.",
        )
    except Exception as e:
        logger.warning(
            "upcoming_file_load_failed",
            extra={"path": UPCOMING_FILE, "error": str(e)},
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to load upcoming games data.",
        )

    return data


# -----------------------------------------------------------------------------
# ITAD-based prediction endpoint (for future tooling / debugging)
# -----------------------------------------------------------------------------


@app.post("/predict/from_itad", response_model=PredictFromItadResponse)
async def predict_from_itad(payload: PredictFromItadRequest) -> PredictFromItadResponse:
    """
    Uses ITAD game info + FeatureBuilder to create features, run the model,
    and (optionally) attach single-horizon insights.
    """
    if not itad_client.is_enabled():
        raise HTTPException(status_code=503, detail="ITAD client not configured")

    info = itad_client.get_game_info(payload.itad_id)
    if not info:
        raise HTTPException(
            status_code=404,
            detail="Could not fetch game info from ITAD",
        )

    appid = info.get("appid")
    if appid is None:
        raise HTTPException(
            status_code=400,
            detail="Game info from ITAD missing Steam appid",
        )

    features = feature_builder.build_from_itad(appid=appid, game=info)

    result = model_service.predict(
        horizon=payload.horizon,
        appid=appid,
        features=features,
        threshold=payload.threshold,
    )

    insights = None
    name = info.get("title") or info.get("name")

    if payload.include_insights:
        insights = insight_service.build_insights(
            appid=appid,
            prediction=result,
            features=features,
            game_name=name,
        )

    image_url = _extract_image_url_from_itad(info, appid)

    return PredictFromItadResponse(
        appid=appid,
        horizon=result["horizon"],
        will_discount=result["will_discount"],
        score=result["score"],
        threshold=result["threshold"],
        insights=insights,
        name=name,
        image_url=image_url,
    )