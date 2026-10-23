from pathlib import Path


def prepared_compose(workspace: Path, image: str = "alpine:3.21.3") -> dict:
    return {
        "services": {
            "agent": {
                "image": image,
                "working_dir": "/workspace",
                "volumes": [{"type": "bind", "source": str(workspace), "target": "/workspace"}],
            }
        }
    }
