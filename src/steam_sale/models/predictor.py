from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from pathlib import Path
import json

import numpy as np

# Project imports
from src.steam_sale.config import settings
from src.steam_sale.logging_setup import logger
from src.steam_sale.exceptions import ModelNotLoadedError, BadRequestError

# using joblib for model loading
try:
    import joblib
except Exception as e:
    logger.error(f"Failed to import joblib: {e}")
    raise

class Horizon:
    """
    Helper class to define prediction horizons.
    Callers shoulf pass only 30 days to 60 days
    """

    THIRTY = "30d"
    SIXTY = "60d"

    @staticmethod
    def is_valid(value: str) -> bool:
        """Returns True if the value is a valid horizon."""

        if value == Horizon.THIRTY:
            return True
        if value == Horizon.SIXTY:
            return True
        return False
    
class ItadClient:
    """
    A mock ITAD client for demonstration purposes.
    """

    def __init__(self, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url

    def is_enabled(self) -> bool:
        # Cheking is both key and url are present

        if self.api_key and self.base_url:
            return True
        return False
    
    def enrich_features(self, appid: int, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mock method to enrich features using ITAD data.
        In a real implementation, this would make API calls to ITAD.
        """

        if not self.is_enabled():
            return features
        
        # TO DO (later): call ITAD endpoints and update features safely.
        # Keep a try/except here to avoid breaking predictions on API failure.
        try:
            # Example idea (placeholder):
            # latest_price = self._fetch_latest_price(appid)
            # features["latest_price"] = latest_price
            pass
        except Exception as e:
            logger.warning("itad_enrich_failed", extra={"appid": appid, "error": str(e)})
            return features

        return features
    
@dataclass
class ModelService:
    """
    Service class for loading models and making predictions.
    Holds both 30 days and 60 days models, one shared feature list.
    """

    model_30d: Any | None = None
    model_60d: Any | None = None
    feature_names: List[str] | None = None
    default_threshold: float = 0.5
    itad: ItadClient | None = None

    def load(self) -> None:
        """
        This function loads both 30 days and 60 days models and, 
        feature list from disk excactly once.
        """

        logger.info("loading_model_artifacts")

        # Checking if joblib is available
        if not joblib:
            logger.error("joblib_not_available")
            raise ModelNotLoadedError("joblib is not installed. Run: pip install joblib")
        
        # Resolving model paths
        model_30d_path = Path(getattr(settings, "MODEL_30D_PATH", ""))
        model_60d_path = Path(getattr(settings, "MODEL_60D_PATH", ""))
        features_path = Path(getattr(settings, "FEATURES_PATH", ""))

        # Loading 30 days model
        if not model_30d_path.exists():
            logger.error("model_30d_missing", extra={"path": str(model_30d_path)})
            raise ModelNotLoadedError(f"30d model not found at {model_30d_path}")
        self.model_30d = joblib.load(model_30d_path)

        # Loading 60 days model
        if not model_60d_path.exists():
            logger.error("model_60d_missing", extra={"path": str(model_60d_path)})
            raise ModelNotLoadedError(f"60d model not found at {model_60d_path}")
        self.model_60d = joblib.load(model_60d_path)

        # Loading feature names
        if not features_path.exists():
            logger.error("features_file_missing", extra={"path": str(features_path)})
            raise ModelNotLoadedError(f"Features list not found at {features_path}")
        with open(features_path, "r") as f:
            self.feature_names = json.load(f)

        # Initializing ITAD client if API key is provided
        itad_api_key = getattr(settings, "ITAD_API_KEY", None)
        itad_base_url = getattr(settings, "ITAD_BASE_URL", None) # modify in config if needed
        self.itad = ItadClient(api_key=itad_api_key, base_url=itad_base_url)

        logger.info("model_artifacts_loaded_successfully", extra={
            "model_30d_path": str(model_30d_path),
            "model_60d_path": str(model_60d_path),
            "features_path": str(features_path),
        })

    def _vectorize(self, features: Dict[str, Any]) -> np.ndarray:
        """
        This function accepts a dictionary of features and converts it into a numpy array in the
        order defined by self.feature_names.

        Raises BadRequestError if any feature is missing or not numeric.
        """

        if not self.feature_names:
            raise ModelNotLoadedError("Feature names are not loaded. Did you call load()?")
        
        vector: List[float] = []
        missing: List[str] = []

        # going thhrough all expected features
        for name in self.feature_names:
            if name in features:
                value = features[name]
            else:
                value = None
            
            if value is None:
                # missing feature
                missing.append(name)
            else:
                try:
                    # converting to float
                    numeric_value = float(value)
                    vector.append(numeric_value)
                except (ValueError, TypeError):
                    raise BadRequestError(f"Feature '{name}' must be numeric. Got {value!r}")

        # if there are missing features, raising an error        
        if len(missing) > 0:
            raise BadRequestError(f"Missing required features: {missing}")
        
        arr = np.array(vector, dtype=float)
        arr = arr.reshape(1, -1) # reshaping to 2D array for model input

        return arr
    
    def predict(self, horizon: str, appid: int, features: Dict[str, Any],
                threshold: Optional[float] = None) -> Dict[str, Any]:
        """
        This function uses either the 30 days or 60 days model to make a prediction.
        Args:
            horizon: "30d" or "60d"
            appid: Steam application ID
            features: Dictionary of input features
            threshold: Optional threshold for classification
        Returns:
            Dictionary with prediction results
        """

        # Validating horizon
        if not Horizon.is_valid(horizon):
            raise BadRequestError(f"Invalid horizon: {horizon}. Must be '30d' or '60d'.")
        
        # Ensuring models and features are loaded
        if self.model_30d is None or self.model_60d is None:
            raise ModelNotLoadedError("Models not loaded. Call load() first.")
        
        # Enriching features using ITAD if available
        if self.itad is not None:
            features = self.itad.enrich_features(appid = appid, features=features)

        # Vectorizing features
        X = self._vectorize(features)

        # Selecting the appropriate model
        if horizon == Horizon.THIRTY:
            model = self.model_30d
        else:
            model = self.model_60d

        # making sure model has predict_proba method
        if not hasattr(model, "predict_proba"):
            raise ModelNotLoadedError(f"The selected model for {horizon} does not support probability predictions.")
        
        # predicting probabilities for class 1
        probs = model.predict_proba(X)
        score = float(probs[0][1])

        # deciding the class based on threshold
        if threshold is not None:
            cut  = float(threshold)
        else:
            cut = self.default_threshold

        will_discount = False
        if score >= cut:
            will_discount = True

        # logging the decision
        logger.info("prediction_made", extra={
            "appid": appid,
            "horizon": horizon,
            "score": score,
            "threshold": cut,
            "will_discount": will_discount,
        })

        result = {
            "appid": appid,
            "horizon": horizon,
            "score": score,
            "threshold": cut,
            "will_discount": will_discount,
        }

        return result
    
# Creating a global model service instance
model_service = ModelService()