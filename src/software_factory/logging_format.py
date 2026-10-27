# Format public application logs as JSON Lines using only safe messages and selected factory context.
import json
import logging
from datetime import UTC, datetime


# Serialize the public log schema without arbitrary extras, exception details, or stack traces.
class JsonFormatter(logging.Formatter):
    # Return one JSON record; the ordinary stream handler supplies its terminating newline.
    def format(self, record: logging.LogRecord) -> str:
        fields = {
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "event": getattr(record, "event", "application_log"),
            "message": record.getMessage(),
        }
        for key in ("repository", "issue", "phase", "run_id", "pr_url"):
            value = getattr(record, key, None)
            if value is not None:
                fields[key] = value
        return json.dumps(fields)
