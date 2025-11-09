from src.steam_sale.insights import InsightService

def test_contextual_factors_new_major_publisher_near_sale():
    """
    Scenario:
    - Upcoming/new title
    - Major publisher
    - Near a major Steam sale window
    Expect:
    - Mentions new/upcoming title behavior
    - Mentions major publisher behavior
    - Mentions sale window proximity
    """
    service = InsightService()

    features = {
        "release_year": 2025,
        "publisher_size_bin__Major (>50)": 1,
        "is_summer_sale_window": 1,
        "is_autumn_sale_window": 0,
        "is_holiday_season": 0,
        "within_7d_of_steam_sale": 0,
    }

    factors = service._extract_contextual_factors(features)

    joined = " ".join(factors)

    assert "new or upcoming title" in joined
    assert "major publisher" in joined
    assert "major Steam sale window" in joined


def test_contextual_factors_small_publisher_franchise():
    """
    Scenario:
    - New title
    - Small publisher
    - Part of established franchise
    Expect:
    - Hint about smaller publisher flexibility
    - Hint about franchise promo potential
    """
    service = InsightService()

    features = {
        "release_year": 2025,
        "publisher_size_bin__Small (≤5)": 1,
        "franchise_count_prev": 4,
    }

    factors = service._extract_contextual_factors(features)
    joined = " ".join(factors)

    assert "smaller publisher" in joined.lower()
    assert "franchise" in joined.lower()



def test_contextual_factors_handles_missing_or_bad_values():
    """
    Scenario:
    - Missing or non-numeric values
    Expect:
    - No crash, returns [] or minimal hints
    """
    service = InsightService()

    features = {
        "release_year": "not_a_year",
        "publisher_size_bin__Major (>50)": "weird",
        "franchise_count_prev": "NaN",
    }

    factors = service._extract_contextual_factors(features)

    # We mostly care that this DOES NOT raise, and returns a list.
    assert isinstance(factors, list)