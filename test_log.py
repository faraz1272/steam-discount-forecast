from src.steam_sale.logging_setup import logger

logger.info("App started")
logger.warning("This is a warning message")

try:
    1 / 0
except ZeroDivisionError:
    logger.exception("An error occurred")