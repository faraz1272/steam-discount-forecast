from src.steam_sale.feature_builder import FeatureBuilder

# create an instance (this loads the franchise JSON)
builder = FeatureBuilder()

# simulate a fake ITAD response
fake_game = {
    "title": "Galactic Empires IV",
    "tags": ["Grand Strategy", "4X", "Historical", "Multiplayer"]
}

# empty dict to hold features
f = {}

# --- genre cluster assignment ---
tags = fake_game.get("tags", [])
genre_flags = builder._map_tags_to_genre_clusters(tags)
f["genre_cluster_strategy_sim"] = genre_flags.get("genre_cluster_strategy_sim_y", 0)
f["genre_cluster_mmo"] = genre_flags.get("genre_cluster_mmo_y", 0)

# --- franchise count approximation ---
estimated_franchise_count = 1
if builder.franchise_map:
    for cluster_name, is_active in genre_flags.items():
        if is_active == 1 and cluster_name in builder.franchise_map:
            estimated_franchise_count = int(builder.franchise_map[cluster_name])
            break

f["franchise_count_prev"] = estimated_franchise_count

# show results
print(f)