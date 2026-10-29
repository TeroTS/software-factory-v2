import json
import os
import subprocess
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.environ.get("FACTORY_LIVE_IMAGE_TESTS") != "1", reason="explicit live AWS image test required")
@pytest.mark.parametrize("kind", ["runner", "agent"])
def test_live_build_smoke_test_and_push(kind: str) -> None:
    version = f"e2e-{uuid.uuid4().hex}"
    repository = f"software-factory-{kind}"
    env = {**os.environ, "AWS_REGION": "eu-central-1", "AWS_DEFAULT_REGION": "eu-central-1"}
    lookup = [
        "aws",
        "ecr",
        "describe-images",
        "--region",
        "eu-central-1",
        "--repository-name",
        repository,
        "--image-ids",
        f"imageTag={version}",
        "--output",
        "json",
    ]
    absent = subprocess.run(lookup, capture_output=True, text=True, env=env)
    assert absent.returncode != 0 and "ImageNotFoundException" in absent.stderr, absent.stderr
    image = f"172318459814.dkr.ecr.eu-central-1.amazonaws.com/{repository}:{version}"
    print(f"Publishing test image {image}", flush=True)
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/publish-image"), kind, version], capture_output=True, text=True, env=env
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert image in result.stdout
    found = subprocess.run(lookup, capture_output=True, text=True, env=env, check=True)
    details = json.loads(found.stdout)["imageDetails"]
    assert len(details) == 1 and details[0]["imageDigest"].startswith("sha256:")
    assert version in details[0]["imageTags"]
