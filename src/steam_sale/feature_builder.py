from __future__ import annotations

import math
from datetime import datetime
from typing import Dict, Any

from src.steam_sale.logging_setup import logger

class FeatureBuilder:
    """
    This class is responsible to convert external game metadata into
    features dictionary expected by the prediction model.
    """

    def build_from_itad(self, appid: int, game: Dict[str, Any]) -> Dict[str, Any]:
        """
        This is the main entry for building a feature dict using ITAD-style data.

        Parameters:
        - appid: Steam appid
        - game: dict from ItadClient.get_game_details()

        Returns:
        - features: dict[str, Any] with all required model features.        
        """

        f: Dict[str, Any] = {}

        # getting the launch price of the game
        price = self._extract_launch_price(game)
        if price is None or price <= 0:
            price = 60.0  # defaulting to $60 if unknown
        f["log_launch_price"] = math.log(price)

        # release date other date related features
        release_date = self._extract_release_date(game)
        if release_date is None:
            # fallback to end of year if unknown
            release_date = datetime(datetime.utcnow().year, 12, 1)

        f["release_year"] = release_date.year
        f["release_month"] = release_date.month
        f["release_quarter"] = (release_date.month - 1) // 3 + 1
        f["release_weekday"] = release_date.weekday()

        # seasonal flags
        f["is_holiday_season"] = 1 if release_date.month in (11, 12) else 0
        f["is_summer_sale_window"] = 1 if release_date.month in (6, 7) else 0
        f["is_autumn_sale_window"] = 1 if release_date.month == 10 else 0

        # within_7d_of_steam_sale: simple approximation (major sales by month)
        f["within_7d_of_steam_sale"] = 1 if release_date.month in (6, 11, 12) else 0

        # content flags / platform flags (fallbacks)
        f["early_access"] = int(bool(game.get("early_access", False)))
        f["mature"] = int(bool(game.get("mature", False)))
        f["Achievements"] = int(bool(game.get("achievements", True)))  # default True

        # multi-platform / cross-platform approximations
        platforms = (game.get("platforms") or [])  # e.g., ["pc", "xbox", "ps"]
        is_pc_only = (platforms == ["pc"]) or (platforms == [])
        is_multi_store_pc = bool(game.get("other_pc_stores", []))

        f["is_multiplatform_refined"] = 0 if is_pc_only else 1
        f["exclusive_steam"] = 1 if is_pc_only and not is_multi_store_pc else 0
        f["is_multi_store_pc"] = int(is_multi_store_pc)
        f["is_cross_platform"] = 1 if len(platforms) > 1 else 0

        # publisher / developer size bins (no direct info -> safe defaults)
        # For now: treating unknown as Small/Indie.
        # You can later map this from your historical publisher stats.
        f["publisher_size_log"] = 1.5
        f["developer_size_log"] = 1.2

        f["publisher_size_bin__Small (≤5)"] = 1
        f["publisher_size_bin__Medium (6–15)"] = 0
        f["publisher_size_bin__Large (16–50)"] = 0
        f["publisher_size_bin__Major (>50)"] = 0

        f["developer_size_bin__Solo/Indie (≤2)"] = 1
        f["developer_size_bin__Small (3–5)"] = 0
        f["developer_size_bin__Mid (6–15)"] = 0
        f["developer_size_bin__Large (>15)"] = 0

        # franchise activity (if ITAD provides it, else assume 0)
        f["franchise_count_prev"] = int(game.get("franchise_count", 0))

        # interaction features: coarse approximations
        f["price_x_multiplatform"] = price * f["is_multiplatform_refined"]
        f["publisher_x_multiplatform"] = f["publisher_size_log"] * f["is_multiplatform_refined"]
        f["developer_x_multiplatform"] = f["developer_size_log"] * f["is_multiplatform_refined"]
        f["price_x_pubsize"] = price * f["publisher_size_log"]
        f["price_x_devsize"] = price * f["developer_size_log"]

        # 7) Genre clusters placeholders
        f["genre_cluster_strategy_sim"] = 0
        f["genre_cluster_mmo"] = 0

        # checking for missing keys
        missing = [k for k in [
            "log_launch_price",
            "publisher_size_log",
            "release_year",
            "release_quarter",
            "release_month",
            "release_weekday",
            "is_holiday_season",
            "is_summer_sale_window",
            "early_access",
            "mature",
            "Achievements",
            "is_multiplatform_refined",
            "exclusive_steam",
            "is_multi_store_pc",
            "is_cross_platform",
            "genre_cluster_strategy_sim",
            "genre_cluster_mmo",
            "is_autumn_sale_window",
            "within_7d_of_steam_sale",
            "franchise_count_prev",
            "developer_size_log",
            "publisher_size_bin__Small (≤5)",
            "publisher_size_bin__Medium (6–15)",
            "publisher_size_bin__Large (16–50)",
            "publisher_size_bin__Major (>50)",
            "developer_size_bin__Solo/Indie (≤2)",
            "developer_size_bin__Small (3–5)",
            "developer_size_bin__Mid (6–15)",
            "developer_size_bin__Large (>15)",
            "price_x_multiplatform",
            "publisher_x_multiplatform",
            "developer_x_multiplatform",
            "price_x_pubsize",
            "price_x_devsize",
        ] if k not in f]

        if missing:
            logger.warning(
                "feature_builder_missing_keys",
                extra={"appid": appid, "missing": missing},
            )

        return f
    
    def _extract_launch_price(self, game: Dict[str, Any]) -> float | None:
        price = game.get("price") or game.get("price_usd")
        try:
            if price is None:
                return None
            return float(price)
        except (TypeError, ValueError):
            return None

    def _extract_release_date(self, game: Dict[str, Any]) -> datetime | None:
        raw = (
            game.get("release_date")
            or game.get("released")
            or game.get("date")
        )
        if not raw:
            return None

        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d")
        except Exception:
            return None
        
feature_builder = FeatureBuilder()