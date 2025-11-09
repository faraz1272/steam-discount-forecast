# tests/test_insights_news.py

from src.steam_sale.insights import NewsClient


def test_is_relevant_article_matches_game_name():
    client = NewsClient(api_key="dummy", base_url="https://example.com")

    title = "Cyberpunk 2077 gets big discount in latest Steam sale"
    assert client._is_relevant_article(title, "Cyberpunk 2077") is True


def test_is_relevant_article_matches_sale_keywords():
    client = NewsClient(api_key="dummy", base_url="https://example.com")

    title = "Massive RPG discounts in the latest Steam sale weekend"
    # No game name, but clearly about sale/discount
    assert client._is_relevant_article(title, "Some Unknown Game") is True


def test_is_relevant_article_filters_irrelevant():
    client = NewsClient(api_key="dummy", base_url="https://example.com")

    title = "Asus releases new GPU for AI workloads"
    # No game, no sale/discount wording relevant to us
    assert client._is_relevant_article(title, "Cyberpunk 2077") is False