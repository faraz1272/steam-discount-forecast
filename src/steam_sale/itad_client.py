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
    
itad_client = ItadClient(
    api_key=settings.ITAD_API_KEY,
    base_url=settings.ITAD_BASE_URL or "https://api.isthereanydeal.com",
)