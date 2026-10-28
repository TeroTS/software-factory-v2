# Expose the contracted terminal entrypoint; report startup failures without sensitive tracebacks.
import argparse
import logging
import os
import signal
from pathlib import Path
from types import FrameType

from software_factory.config import load_config
from software_factory.logging_format import JsonFormatter
from software_factory.process import FactoryError
from software_factory.runner import Runner, preflight


# Convert SIGTERM to an interruption so active issue-run cleanup and failure reporting still execute.
def stop(signum: int, frame: FrameType | None) -> None:
    raise KeyboardInterrupt


# Validate startup and run polling; return nonzero on failure or operator interruption.
def main() -> int:
    parser = argparse.ArgumentParser(description="Local autonomous coding factory")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    logger = logging.getLogger("software_factory")
    previous = signal.signal(signal.SIGTERM, stop)
    try:
        config = load_config(args.config)
        logger = logging.LoggerAdapter(logger, {"repository": config.repository}, merge_extra=True)
        selected = os.environ.get("AGENT_IMAGE")
        if selected is not None and config.agent_image != selected:
            raise FactoryError("TOML agent_image must match the selected AGENT_IMAGE; select/configure while stopped")
        runtime = preflight(config)
        Runner(config, runtime).run()
    except FactoryError as error:
        logger.error("%s", error, extra={"event": "runner_failed"})
        return 1
    except OSError:
        logger.error(
            "Cannot initialize local factory files; check paths and permissions", extra={"event": "runner_failed"}
        )
        return 1
    except KeyboardInterrupt:
        logger.info("Runner stopped by operator", extra={"event": "runner_interrupted"})
        return 130
    finally:
        signal.signal(signal.SIGTERM, previous)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
