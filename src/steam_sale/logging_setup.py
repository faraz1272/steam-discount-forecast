import logging
import json
import sys
from datetime import datetime


class JsonFormatter(logging.Formatter):
    """Custom formatter that outputs logs as JSON instead of plain text."""

    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + 'Z',
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)
    

logger = logging.getLogger("steam_sale")

handler = logging.StreamHandler(sys.stdout)

handler.setFormatter(JsonFormatter())

logger.setLevel(logging.INFO)

logger.addHandler(handler)

logger.propagate = False