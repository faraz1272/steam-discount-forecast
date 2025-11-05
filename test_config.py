# test_config.py
from src.steam_sale.config import settings

print(settings.APP_ENV)
print(settings.MODEL_PATH)
print(settings.OPENAI_API_KEY)
print(settings.ITAD_API_KEY)
print(settings.RAWG_API_KEY)