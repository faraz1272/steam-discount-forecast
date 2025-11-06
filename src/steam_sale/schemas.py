from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field, field_validator

class PredictRequest(BaseModel):
    """
    This class defines what the client should send to the prediction endpoint.
    Pydantic will validate the incoming request against this schema.
    """

    # Steam App ID of the game to predict(e.g. 570 for Dota 2)
    appid: int = Field(..., description="Steam app id")

    # Only 30d or 60d are valid options
    horizon: Literal["30d", "60d"] = Field(..., description="Prediction horizon: '30d' or '60d'")

    # Dictionary of input features required by the model
    # Features must include all names defined in feature_list.json
    features: Dict[str, Any] = Field(..., description="Feature mapping: name to value (must match feature_list.json)")

    # Optional threshold for classification
    threshold: Optional[float] = Field(None, description="Optional probability cutoff override (0 to 1)")

    @field_validator("features")
    @classmethod
    def ensure_no_empty_features(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        """
        This fucntion checks that the features dictionary is not empty.
        """

        if value is None:
            raise ValueError("Features must be provided")
        if len(value) == 0:
            raise ValueError("features cannnot be empty")
        return value
    
class PredictResponse(BaseModel):
    """
    This class defines the response schema to the caller after running the prediction.
    """

    appid: int
    horizon: Literal["30d", "60d"]
    will_discount: bool
    score: float
    threshold: float

class HealthResponse(BaseModel):
    """
    This class defines the response schema for the health check endpoint.
    """

    status: Literal["ok"]
    model_30d_loaded: bool
    model_60d_loaded: bool