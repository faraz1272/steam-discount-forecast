from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from src.steam_sale.config import settings
from src.steam_sale.logging_setup import logger

class ItadClient:
    """
    A small wrapper class to interact with the ITAD API.

    Responsibilities:
    - Search games by name.
    - Fetch game details for a given steam appid.
    """

    def __init__(self, api_key: Optional[str], base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def is_enabled(self) -> bool:
        # Cheking is both key and url are present

        if self.api_key and self.base_url:
            return True
        return False
    
    def _get(self, path: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Internal helpper to make GET requests to ITAD API.
        Returns the JSON response as a dictionary or None on failure.
        """
        
        if not self.is_enabled():
            return None
        
        url = f"{self.base_url}/{path.lstrip('/')}"
        all_params = {"key": self.api_key}
        all_params.update(params)

        try:
            resp = requests.get(url, params=all_params, timeout=3.0)
            if resp.status_code != 200:
                logger.warning(
                    "itad_request_non_200",
                    extra={
                        "path": path,
                        "status_code": resp.status_code,
                        "body_snippet": resp.text[:200],
                    },
                )
                return None
            return resp.json()
        except Exception as e:
            logger.warning(
                "itad_request_failed",
                extra={"path": path, "error": str(e)},
            )
            return None
        
    def _post(self, path: str, json_body: Any, params: Dict[str, Any]) -> Optional[Any]:
        """
        Internal POST helper.
        Adds ?key=... and handles errors safely.
        Returns parsed JSON (list or dict) or None on error.
        """
        if not self.is_enabled():
            return None

        url = f"{self.base_url}{path}"

        all_params = {"key": self.api_key}
        all_params.update(params)

        try:
            resp = requests.post(url, params=all_params, json=json_body, timeout=5.0)

            if resp.status_code != 200:
                logger.warning(
                    "itad_post_non_200",
                    extra={
                        "path": path,
                        "status_code": resp.status_code,
                        "body_snippet": resp.text[:200].replace("\n", " "),
                    },
                )
                return None

            return resp.json()

        except Exception as e:
            logger.warning(
                "itad_post_failed",
                extra={"path": path, "error": str(e)},
            )
            return None


    def search_game(self, title: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Searches for games matching the query string.
        Returns list of:
        { "itad_id": int | None, "title": str, "release_date": str | None }       
        """

        if not self.is_enabled():
            return []
        
        data = self._get(
           "/games/search/v1",
            {"title": title, "results": limit},
        )

        if not data:
            return []
        
        items = data if isinstance(data, list) else data.get("results") or []
        
        results: List[Dict[str, Any]] = []

        for item in items:
            itad_id = item.get("id")
            name = item.get("title")
            if not itad_id or not name:
                continue
            results.append(
                {
                    "itad_id": itad_id,
                    "title": name,
                }
            )
            if len(results) >= limit:
                break

        return results
    
    def get_game_info(self, itad_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetches detailed game info for a given ITAD game ID.
        Returns a dictionary of game details or None on failure.
        """

        if not self.is_enabled():
            return None
        
        data = self._get("/games/info/v2", {"id": itad_id})
        if not data:
            return None
        
        return data
    
    def get_price_overview_v3(self, itad_ids: list[str], country: str = "US") -> list[dict]:
        """
        Calls /games/prices/v3 for one or more ITAD IDs.
        Returns the raw list (one element per id).
        """
        url = f"{self.base_url}/games/prices/v3"
        params = {"country": country, "key": self.api_key}
        resp = requests.post(url, params=params, json=itad_ids, timeout=5)
        resp.raise_for_status()
        return resp.json() or []
    
    def pick_current_price(self, price_block: dict, prefer_shops: tuple[int, ...] = (61,)) -> tuple[float | None, str | None, str | None]:
        """
        From a single element of /games/prices/v3 (the object for one game),
        choose a 'current' price:
          1) Prefer Steam (shop id 61) if present.
          2) Otherwise pick the lowest 'price.amount' across deals.
        Returns: (amount, currency, shop_name) or (None, None, None) if not found.
        """
        deals = (price_block or {}).get("deals") or []
        if not deals:
            return None, None, None

        # 1) Prefer Steam (or any preferred shops)
        for d in deals:
            shop = (d.get("shop") or {})
            if shop.get("id") in prefer_shops:
                p = d.get("price") or {}
                return p.get("amount"), p.get("currency"), shop.get("name")

        # 2) Else lowest across all deals
        best = None
        for d in deals:
            p = d.get("price") or {}
            amt = p.get("amount")
            if isinstance(amt, (int, float)):
                if best is None or amt < best[0]:
                    shop = (d.get("shop") or {})
                    best = (amt, p.get("currency"), shop.get("name"))
        return best if best else (None, None, None)

    def get_current_price_simple(self, itad_id: str, country: str = "US") -> tuple[float | None, str | None, str | None]:
        """
        Convenience wrapper for a single game id.
        """
        data = self.get_price_overview_v3([itad_id], country=country)
        if not data:
            return None, None, None
        return self.pick_current_price(data[0])

    @staticmethod
    def extract_best_price_from_prices(entry: dict) -> float | None:
        """
        From one /games/prices/v3 entry, return lowest 'price.amount' across 'deals'.
        """
        try:
            deals = entry.get("deals") or []
            amounts = []
            for d in deals:
                p = (d.get("price") or {}).get("amount")
                if p is not None:
                    amounts.append(float(p))
            return min(amounts) if amounts else None
        except Exception:
            return None
    
    def get_game_shops(self, itad_id: str) -> list[str]:
        """
        Gets list of shop names (e.g. Steam, GOG, Epic) where this game appears.
        Uses:
          POST /games/prices/v3
        Ignores prices, only care about which shops exist.
        """
        if not self.is_enabled():
            return []

        data = self._post(
            path="/games/prices/v3",
            json_body=[itad_id],          # API expects a list of game IDs
            params={},
        )

        if not data or not isinstance(data, list):
            return []

        entry = data[0] if data else {}
        deals = entry.get("deals") or []

        shops: set[str] = set()
        for deal in deals:
            shop = deal.get("shop")
            if not shop:
                continue

            # If API returns {"id": "...", "name": "..."} or similar
            if isinstance(shop, dict):
                shop_name = shop.get("name") or shop.get("id")
                if shop_name:
                    shops.add(str(shop_name))
            # If it's already a string like "Steam"
            elif isinstance(shop, str):
                shops.add(shop)

        return list(shops)
    
itad_client = ItadClient(
    api_key=settings.ITAD_API_KEY,
    base_url=settings.ITAD_BASE_URL or "https://api.isthereanydeal.com",
)