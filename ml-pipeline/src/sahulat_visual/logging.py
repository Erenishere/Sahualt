import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        value = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        standard = logging.LogRecord("", 0, "", 0, "", (), None).__dict__
        value.update(
            {
                k: v
                for k, v in record.__dict__.items()
                if k not in standard and k not in {"message", "asctime"}
            }
        )
        return json.dumps(value, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    # Third-party HTTP logs may contain signed download URLs; keep those private.
    for name in ("httpx", "urllib3", "huggingface_hub"):
        logging.getLogger(name).setLevel(logging.ERROR)
