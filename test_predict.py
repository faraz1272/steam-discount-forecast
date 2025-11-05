# run_predict_demo.py (in project root for a quick check)
from src.steam_sale.models.predictor import model_service

# 1) Load artifacts once
model_service.load()

# 2) Prepare features (must contain all names in your feature list)
features = {
    "log_launch_price": 3.1,
    "publisher_size_log": 2.3,
    "release_year": 2020,
    "release_quarter": 2,
    "release_month": 6,
    "release_weekday": 4,
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
    "franchise_count_prev": 2,
    "developer_size_log": 1.9,
    "publisher_size_bin__Small (≤5)": 0,
    "publisher_size_bin__Medium (6–15)": 1,
    "publisher_size_bin__Large (16–50)": 0,
    "publisher_size_bin__Major (>50)": 0,
    "developer_size_bin__Solo/Indie (≤2)": 0,
    "developer_size_bin__Small (3–5)": 0,
    "developer_size_bin__Mid (6–15)": 1,
    "developer_size_bin__Large (>15)": 0,
    "price_x_multiplatform": 12.0,
    "publisher_x_multiplatform": 6.0,
    "developer_x_multiplatform": 4.0,
    "price_x_pubsize": 10.0,
    "price_x_devsize": 8.0
}

# Ensure your key names exactly match your feature_list.json

# 3) Predict for 30d
out_30 = model_service.predict(horizon="30d", appid=480, features=features)
print(out_30)

# 4) Predict for 60d
out_60 = model_service.predict(horizon="60d", appid=480, features=features)
print(out_60)