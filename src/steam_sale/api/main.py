from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from time import perf_counter

from src.steam_sale.config import settings
from src.steam_sale.logging_setup import logger
from src.steam_sale.models.predictor import model_service
from src.steam_sale.schemas import PredictRequest, PredictResponse, HealthResponse
from src.steam_sale.exceptions import SteamSaleError, ModelNotLoadedError, BadRequestError
from src.steam_sale.insights import insight_service


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