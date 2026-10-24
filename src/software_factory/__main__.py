# Expose the contracted terminal entrypoint; report startup failures without sensitive tracebacks.
import argparse
import logging
import signal
from pathlib import Path
from types import FrameType

from software_factory.config import load_config
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
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    previous = signal.signal(signal.SIGTERM, stop)
    try:
        config = load_config(args.config)
        runtime = preflight(config)
        Runner(config, runtime).run()
    except FactoryError as error:
        logging.getLogger("software_factory").error("%s", error)
        return 1
    except OSError:
        logging.getLogger("software_factory").error(
            "Cannot initialize local factory files; check paths and permissions"
        )
        return 1
    except KeyboardInterrupt:
        return 130
    finally:
        signal.signal(signal.SIGTERM, previous)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
