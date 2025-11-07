from fastapi.testclient import TestClient
from src.steam_sale.api.main import app

client = TestClient(app)

def test_health_ok():
    """
    Test the /health endpoint to ensure it returns the correct status.
    """

    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()

    assert "status" in data
    assert "model_30d_loaded" in data
    assert "model_60d_loaded" in data

def test_predict_valid_request():
    """
    End-to-end test for /predict:
    - Sends a minimal valid body with correct horizon and features
    - Expects 200 and proper JSON fields
    """

    features = {
        "log_launch_price": 3.1,
        "publisher_size_log": 2.3,
        "release_year": 2020,
        "release_quarter": 2,
        "release_month": 6,
        "release_weekday": 3,
        "is_holiday_season": 0,
        "is_summer_sale_window": 1,
        "early_access": 0,
        "mature": 0,
        "Achievements": 1,
        "is_multiplatform_refined": 1,
        "exclusive_steam": 0,
        "is_multi_store_pc": 1,
        "is_cross_platform": 1,
        "genre_cluster_strategy_sim": 0,
        "genre_cluster_mmo": 0,
        "is_autumn_sale_window": 0,
        "within_7d_of_steam_sale": 0,
        "franchise_count_prev": 1,
        "developer_size_log": 1.5,
        "publisher_size_bin__Small (≤5)": 0,
        "publisher_size_bin__Medium (6–15)": 1,
        "publisher_size_bin__Large (16–50)": 0,
        "publisher_size_bin__Major (>50)": 0,
        "developer_size_bin__Solo/Indie (≤2)": 0,
        "developer_size_bin__Small (3–5)": 0,
        "developer_size_bin__Mid (6–15)": 1,
        "developer_size_bin__Large (>15)": 0,
        "price_x_multiplatform": 10.0,
        "publisher_x_multiplatform": 5.0,
        "developer_x_multiplatform": 3.0,
        "price_x_pubsize": 8.0,
        "price_x_devsize": 6.0,
    }

    payload = {
        "appid": 480,
        "horizon": "30d",
        "features": features
    }

    response = client.post("/predict", json=payload)
    assert response.status_code == 200

    data = response.json()

    assert data["appid"] == 480
    assert data["horizon"] == "30d"
    assert "will_discount" in data
    assert "score" in data
    assert "threshold" in data

def test_predict_rejects_invalid_horizon():
    """
    Test that /predict rejects requests with an invalid horizon value.
    """

    payload = {
        "appid": 480,
        "horizon": "45d",  # Invalid horizon
        "features": {'log_launch_price': 3.1}  # Minimal features for test
    }

    response = client.post("/predict", json=payload)

    assert response.status_code in (400, 422)