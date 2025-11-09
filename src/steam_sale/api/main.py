from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from time import perf_counter
from typing import List

from src.steam_sale.config import settings
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
from src.steam_sale.exceptions import SteamSaleError, ModelNotLoadedError, BadRequestError
from src.steam_sale.insights import insight_service
from src.steam_sale.itad_client import itad_client
from src.steam_sale.feature_builder import feature_builder


app = FastAPI(
    title=settings.APP_NAME if hasattr(settings, "APP_NAME") else "Steam Sale Prediction API",
    default_response_class=JSONResponse,
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Middleware that logs each HTTP request:
    - method (GET/POST)
    - path (/predict, /health, etc.)
    - status code (200, 400, 500...)
    - how long it took (ms)
    """
    start_time = perf_counter()  # recording the time before handling the request

    response = await call_next(request)  # waiting for FastAPI to process the request

    end_time = perf_counter()  # recording the time after response is ready
    duration_ms = (end_time - start_time) * 1000.0  # converting to milliseconds

    # Using JSON logger so logs are structured and machine-readable
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

@app.on_event("startup")
async def startup_event():
    try:
        model_service.load()
        logger.info("startup_complete", extra={"env": settings.APP_ENV})
    except SteamSaleError as e:
        logger.exception("startup_failed", extra={"error": str(e)})

# Health check endpoint
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Checks if the models are loaded and the servie is reunning."""

    loaded_30 = model_service.model_30d is not None
    loaded_60 = model_service.model_60d is not None

    if loaded_30 and loaded_60:
        status = "healthy"
    else:
        status = "loading"

    return HealthResponse(
        status=status,
        model_30d_loaded=loaded_30,
        model_60d_loaded=loaded_60,
    )

@app.post("/predict", response_model=PredictResponse)
async def predict(payload: PredictRequest,
                  include_insights: bool = Query(False, description="If true, inclue insights in response")):
    """This is the main prediction endpoint.
    It accepts a PredictRequest, calls model_service to get a prediction,
    and returns a PredictResponse.
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
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
    except Exception as e:
        logger.exception("unhandled_error")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")
    
    
# Mock data for upcoming games (for now).
# Later you will replace this with real ingested data.
SAMPLE_UPCOMING_GAMES = [
    {
        "appid": 999001,
        "name": "Starfall Tactics",
        "release_date": "2025-12-10",
        "image_url": "https://steamcdn-a.akamaihd.net/steam/apps/999001/header.jpg",
        # Minimal example features; in your real version make sure all required features are filled.
        "features": {
            "log_launch_price": 3.9,
            "publisher_size_log": 3.2,
            "release_year": 2025,
            "release_quarter": 4,
            "release_month": 12,
            "release_weekday": 3,
            "is_holiday_season": 1,
            "is_summer_sale_window": 0,
            "early_access": 0,
            "mature": 0,
            "Achievements": 1,
            "is_multiplatform_refined": 1,
            "exclusive_steam": 0,
            "is_multi_store_pc": 1,
            "is_cross_platform": 1,
            "genre_cluster_strategy_sim": 0,
            "genre_cluster_mmo": 0,
            "is_autumn_sale_window": 0,
            "within_7d_of_steam_sale": 0,
            "franchise_count_prev": 1,
            "developer_size_log": 2.5,
            "publisher_size_bin__Small (≤5)": 0,
            "publisher_size_bin__Medium (6–15)": 0,
            "publisher_size_bin__Large (16–50)": 0,
            "publisher_size_bin__Major (>50)": 1,
            "developer_size_bin__Solo/Indie (≤2)": 0,
            "developer_size_bin__Small (3–5)": 0,
            "developer_size_bin__Mid (6–15)": 1,
            "developer_size_bin__Large (>15)": 0,
            "price_x_multiplatform": 15.0,
            "publisher_x_multiplatform": 8.0,
            "developer_x_multiplatform": 5.0,
            "price_x_pubsize": 10.0,
            "price_x_devsize": 7.5,
        },
    },
    {
        "appid": 999002,
        "name": "Neon Outlaws",
        "release_date": "2026-01-20",
        "image_url": "https://steamcdn-a.akamaihd.net/steam/apps/999002/header.jpg",
        "features": {
            "log_launch_price": 3.4,
            "publisher_size_log": 1.4,
            "release_year": 2026,
            "release_quarter": 1,
            "release_month": 1,
            "release_weekday": 2,
            "is_holiday_season": 0,
            "is_summer_sale_window": 0,
            "early_access": 1,
            "mature": 0,
            "Achievements": 1,
            "is_multiplatform_refined": 0,
            "exclusive_steam": 1,
            "is_multi_store_pc": 0,
            "is_cross_platform": 0,
            "genre_cluster_strategy_sim": 0,
            "genre_cluster_mmo": 0,
            "is_autumn_sale_window": 0,
            "within_7d_of_steam_sale": 0,
            "franchise_count_prev": 0,
            "developer_size_log": 1.2,
            "publisher_size_bin__Small (≤5)": 1,
            "publisher_size_bin__Medium (6–15)": 0,
            "publisher_size_bin__Large (16–50)": 0,
            "publisher_size_bin__Major (>50)": 0,
            "developer_size_bin__Solo/Indie (≤2)": 1,
            "developer_size_bin__Small (3–5)": 0,
            "developer_size_bin__Mid (6–15)": 0,
            "developer_size_bin__Large (>15)": 0,
            "price_x_multiplatform": 0.0,
            "publisher_x_multiplatform": 0.0,
            "developer_x_multiplatform": 0.0,
            "price_x_pubsize": 5.0,
            "price_x_devsize": 4.0,
        },
    },
]
    
    
@app.get("/games/upcoming", response_model=List[UpcomingGame])
async def get_upcoming_games():
    """
    Returns a small list of upcoming games with:
    - image, name, release_date
    - model prediction (uses existing ModelService)
    - insights (using InsightsService)

    For now this uses SAMPLE_UPCOMING_GAMES.
    Later will be replaced with a real ingestion pipeline.
    """

    upcoming: List[UpcomingGame] = []

    for game in SAMPLE_UPCOMING_GAMES:
        appid = game["appid"]
        name = game["name"]
        release_date = game["release_date"]
        image_url = game["image_url"]
        features = game["features"]

        try:
            result = model_service.predict(
                horizon="30d",
                appid=appid,
                features=features,
                threshold=None,
            )

            insights = insight_service.build_insights(
                appid=appid,
                prediction=result,
                features=features,
                game_name=name,
            )

            upcoming.append(
                UpcomingGame(
                    appid=appid,
                    name=name,
                    release_date=release_date,
                    image_url=image_url,
                    horizon=result["horizon"],
                    will_discount=result["will_discount"],
                    score=result["score"],
                    threshold=result["threshold"],
                    insights=insights,
                )
            )

        except Exception as e:
            logger.warning(
                "upcoming_game_prediction_failed",
                extra={"appid": appid, "game_name": name, "error": str(e)},
            )
            continue

    return upcoming

@app.get("/games/search")
async def search_games(title: str, limit: int = 5):
    """
    Search for games by title using ITAD.
    Returns a list of possible matches with their itad_id and name.
    """
    if not itad_client.is_enabled():
        raise HTTPException(status_code=503, detail="ITAD client not configured")

    results = itad_client.search_game(title=title, limit=limit)
    if not results:
        raise HTTPException(status_code=404, detail="No results found")

    return results

@app.post("/predict/from_itad", response_model=PredictFromItadResponse)
async def predict_from_itad(payload: PredictFromItadRequest) -> PredictFromItadResponse:
    """
    Uses ITAD game info + our FeatureBuilder to create features,
    then run the model and attach insights.

    Flow:
    - takes itad_id from client (selected from /games/search)
    - fetches game info from ITAD
    - builds features
    - calls model_service.predict(...)
    - optionally add insights
    """
    if not itad_client.is_enabled():
        raise HTTPException(status_code=503, detail="ITAD client not configured")

    # fetching detailed info from ITAD
    info = itad_client.get_game_info(payload.itad_id)
    if not info:
        raise HTTPException(status_code=404, detail="Could not fetch game info from ITAD")

    # getting appid from the info payload
    appid = info.get("appid")
    if appid is None:
        raise HTTPException(status_code=400, detail="Game info from ITAD missing Steam appid")

    # building model features from ITAD data
    features = feature_builder.build_from_itad(appid=appid, game=info)

    # running prediction using ModelService
    result = model_service.predict(
        horizon=payload.horizon,
        appid=appid,
        features=features,
        threshold=payload.threshold,
    )

    # optional insights
    insights = None
    if payload.include_insights:
        name = info.get("title") or info.get("name")
        insights = insight_service.build_insights(
            appid=appid,
            prediction=result,
            features=features,
            game_name=name,
        )
    else:
        name = info.get("title") or info.get("name")

    # image URL for UI
    image_url = f"https://steamcdn-a.akamaihd.net/steam/apps/{appid}/header.jpg"

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
