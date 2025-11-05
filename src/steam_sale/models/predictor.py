from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from pathlib import Path
import json

import numpy as np

# Project imports
from steam_sale.config import settings
from steam_sale.logging_setup import logger
from steam_sale.exceptions import ModelNotLoadedError, BadRequestError

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