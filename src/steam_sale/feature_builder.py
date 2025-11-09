from __future__ import annotations
import os
import json

import math
from datetime import datetime
from typing import Dict, Any

from src.steam_sale.logging_setup import logger
from src.steam_sale.itad_client import itad_client

class FeatureBuilder:
    """
    This class is responsible to convert external game metadata into
    features dictionary expected by the prediction model.
    """

    def __init__(self):
        self.franchise_map = self._load_franchise_map()

    def _load_franchise_map(self) -> dict[str, float]:
        """
        Loads median franchise counts per genre cluster from artifacts.
        Returns an empty dict if file missing.
        """
        path = os.path.join(
            os.path.dirname(__file__),
            "../../artifacts/models_at_inference/median_franchise_count_prev_per_cluster.json"
        )
        path = os.path.abspath(path)

        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Could not load franchise median map: {e}")
            return {}
        
    def _map_tags_to_genre_clusters(self, tags: list[str]) -> dict[str, int]:
        """
        Converts ITAD tags into genre cluster binary flags.
        """
        tags_lower = [t.lower() for t in tags]

        return {
            "genre_cluster_strategy_sim_y": int(any(t in tags_lower for t in ["strategy", "simulation", "4x", "grand strategy"])),
            "genre_cluster_mmo_y": int(any(t in tags_lower for t in ["mmo", "online", "multiplayer"])),
            "genre_cluster_story_action_mainstream": int(any(t in tags_lower for t in ["action", "adventure", "story", "rpg"])),
            "genre_cluster_sports_competitive": int(any(t in tags_lower for t in ["sports", "racing", "competitive"])),
        }

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

        # shops / multi-store PC / "exclusive Steam" from ITAD
        is_multi_store_pc = 0
        exclusive_steam = 0
        is_multiplatform_refined = 0  # for now: based on PC store spread
        is_cross_platform = 0         # 0 for now, could be enhanced later

        itad_id = game.get("id")
        if itad_id and itad_client.is_enabled():
            shops = itad_client.get_game_shops(itad_id)

            if shops:
                # defining which shops are treated as PC stores
                pc_shops = {
                    "Steam",
                    "GOG",
                    "Epic Games Store",
                    "Humble Store",
                    "Green Man Gaming",
                    "Fanatical",
                }

                pc_present = [s for s in shops if s in pc_shops]

                # Multi-store PC: game sold on more than one PC shop
                if len(pc_present) > 1:
                    is_multi_store_pc = 1

                # Exclusive Steam: only Steam among known PC shops
                if pc_present and all(s == "Steam" for s in pc_present):
                    exclusive_steam = 1

                # For v1: treating "available on multiple PC stores" as refined multiplatform signal.
                if is_multi_store_pc:
                    is_multiplatform_refined = 1

        # Store results in feature dict
        f["is_multi_store_pc"] = is_multi_store_pc
        f["exclusive_steam"] = exclusive_steam
        f["is_multiplatform_refined"] = is_multiplatform_refined
        f["is_cross_platform"] = is_cross_platform

        # publisher / developer size estimated from launch price.
        # using the same heuristic for both - it's a proxy, not exact truth.
        pub_size_log, pub_bins = self._estimate_size_from_price(price)
        f["publisher_size_log"] = pub_size_log
        f["publisher_size_bin__Small (≤5)"] = pub_bins["Small (≤5)"]
        f["publisher_size_bin__Medium (6–15)"] = pub_bins["Medium (6–15)"]
        f["publisher_size_bin__Large (16–50)"] = pub_bins["Large (16–50)"]
        f["publisher_size_bin__Major (>50)"] = pub_bins["Major (>50)"]

        # reusing the same heuristic, but mapping to developer bins.
        dev_size_log, dev_bins = self._estimate_size_from_price(price)
        f["developer_size_log"] = dev_size_log
        f["developer_size_bin__Solo/Indie (≤2)"] = dev_bins["Small (≤5)"]
        f["developer_size_bin__Small (3–5)"] = dev_bins["Medium (6–15)"]
        f["developer_size_bin__Mid (6–15)"] = dev_bins["Large (16–50)"]
        f["developer_size_bin__Large (>15)"] = dev_bins["Major (>50)"]

        # --- Franchise count approximation ---
        # default value if I can't estimate anything
        estimated_franchise_count = 1

        # getting the game's tags (from ITAD)
        tags = game.get("tags", [])

        # using helper to map tags into genre clusters
        genre_flags = self._map_tags_to_genre_clusters(tags)

        # checking which genre cluster is active (has value 1)
        # and looking up the corresponding median from self.franchise_map
        if self.franchise_map:
            for cluster_name, is_active in genre_flags.items():
                if is_active == 1:
                    # checking if this cluster exists in our median file
                    if cluster_name in self.franchise_map:
                        estimated_franchise_count = int(self.franchise_map[cluster_name])
                        break  # stops after first match

        # finally, assigning the estimated value
        f["franchise_count_prev"] = estimated_franchise_count

        # interaction features: coarse approximations
        f["price_x_multiplatform"] = price * f["is_multiplatform_refined"]
        f["publisher_x_multiplatform"] = f["publisher_size_log"] * f["is_multiplatform_refined"]
        f["developer_x_multiplatform"] = f["developer_size_log"] * f["is_multiplatform_refined"]
        f["price_x_pubsize"] = price * f["publisher_size_log"]
        f["price_x_devsize"] = price * f["developer_size_log"]


        # assigning values for genre cluster features
        f["genre_cluster_strategy_sim"] = genre_flags.get("genre_cluster_strategy_sim_y", 0)
        f["genre_cluster_mmo"] = genre_flags.get("genre_cluster_mmo_y", 0)

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
        
    def _estimate_size_from_price(self, price: float) -> tuple[float, dict[str, int]]:
        """
        Estimates a 'size' for publisher/developer based only on launch price.

        Returns:
        - size_log: a smooth numeric value.
        - bins: a dict for the one-hot size bins:
            {
                "Small (≤5)": 0/1,
                "Medium (6–15)": 0/1,
                "Large (16–50)": 0/1,
                "Major (>50)": 0/1,
            }

        Heuristic:
        - < $15        -> Small
        - $15–29.99    -> Medium
        - $30–49.99    -> Large
        - ≥ $50        -> Major
        """

        if price is None or price <= 0:
            price = 10.0

        # deciding bins from price
        if price < 15:
            size_bin = "Small (≤5)"
            size_log = 1.2  # typical small/indie
        elif price < 30:
            size_bin = "Medium (6–15)"
            size_log = 2.0
        elif price < 50:
            size_bin = "Large (16–50)"
            size_log = 2.7
        else:
            size_bin = "Major (>50)"
            size_log = 3.4

        # building one-hot for bins
        bins = {
            "Small (≤5)": 0,
            "Medium (6–15)": 0,
            "Large (16–50)": 0,
            "Major (>50)": 0,
        }
        bins[size_bin] = 1

        return size_log, bins
        
feature_builder = FeatureBuilder()