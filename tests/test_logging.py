import io
import json
import logging
import sys
from datetime import datetime

import pytest


def test_formatter_emits_only_required_fields_with_utc_timestamp() -> None:
    from software_factory.logging_format import JsonFormatter

    record = logging.LogRecord("software_factory", logging.INFO, __file__, 1, "Running %s", ("checks",), None)
    record.created = 1793102400
    result = json.loads(JsonFormatter().format(record))
    assert result == {
        "timestamp": "2026-10-27T12:00:00.000Z",
        "level": "INFO",
        "event": "application_log",
        "message": "Running checks",
    }
    assert datetime.fromisoformat(result["timestamp"]).utcoffset().total_seconds() == 0


@pytest.mark.parametrize("include_context", [False, True])
def test_formatter_allowlists_context_and_excludes_exception_details(include_context: bool) -> None:
    from software_factory.logging_format import JsonFormatter

    try:
        raise ValueError("private exception detail")
    except ValueError:
        record = logging.LogRecord("software_factory", logging.ERROR, __file__, 1, "Safe failure", (), sys.exc_info())
    context = {
        "repository": "owner/repo",
        "issue": 7,
        "phase": "verification",
        "run_id": "factory-existing-identity",
        "pr_url": "https://github.com/owner/repo/pull/3",
    }
    record.__dict__.update(dict.fromkeys(context))
    if include_context:
        record.__dict__.update(context)
    record.event = "issue_failed"
    record.secret = "private token"
    record.stack_info = "private stack detail"
    encoded = JsonFormatter().format(record)
    result = json.loads(encoded)
    assert result["event"] == "issue_failed"
    assert result["message"] == "Safe failure"
    assert set(result) == {"timestamp", "level", "event", "message"} | (set(context) if include_context else set())
    if include_context:
        assert context.items() <= result.items()
    assert "private" not in encoded


def test_stream_handler_adds_exactly_one_newline_for_multiline_messages() -> None:
    from software_factory.logging_format import JsonFormatter

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    record = logging.LogRecord("software_factory", logging.INFO, __file__, 1, "Line one\nLine two\r\n", (), None)
    handler.handle(record)
    assert len(stream.getvalue().splitlines()) == 1
    assert stream.getvalue().endswith("\n")
    assert json.loads(stream.getvalue())["message"] == "Line one\nLine two\r\n"
