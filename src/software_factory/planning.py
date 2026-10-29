# Validate operator-owned local ticket plans without executing their contents or contacting GitHub.
import argparse
import json
import re
import sys
from pathlib import Path

from software_factory.process import FactoryError


# Reject duplicate JSON object keys rather than silently accepting the last value.
def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


# Reject nonstandard JSON numeric constants such as NaN and Infinity.
def _constant(value: str) -> None:
    raise ValueError("invalid JSON constant")


# Require exactly the contract's fields and return the validated object.
def _fields(value: object, keys: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise FactoryError("Invalid plan: object has missing or unknown fields")
    return value


# Check nonempty narrative text and reserve the generated-ticket metadata opener.
def _narrative(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and "<!-- software-factory:planning" not in value


# Validate exact plan shape, provenance syntax, unique story identities and the dependency DAG.
def validate_plan(value: object) -> None:
    plan = _fields(value, {"version", "repository", "spec_id", "source", "stories"})
    if type(plan["version"]) is not int or plan["version"] != 1:
        raise FactoryError("Invalid plan: unsupported version")
    repository = plan["repository"]
    if (
        not isinstance(repository, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+", repository)
        or repository.split("/")[1] in {".", ".."}
    ):
        raise FactoryError("Invalid plan: repository must be owner/name")
    if not isinstance(plan["spec_id"], str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", plan["spec_id"]):
        raise FactoryError("Invalid plan: invalid spec ID")
    source = _fields(plan["source"], {"path", "commit"})
    path, commit = source["path"], source["commit"]
    if not isinstance(path, str) or "\x00" in path or any(part in {"", ".", ".."} for part in path.split("/")):
        raise FactoryError("Invalid plan: source path must be repository-relative")
    if commit is not None and (
        not isinstance(commit, str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit)
    ):
        raise FactoryError("Invalid plan: source commit must be a full lowercase object ID or null")
    stories = plan["stories"]
    if not isinstance(stories, list) or not stories:
        raise FactoryError("Invalid plan: stories must be a nonempty array")
    dependencies = {}
    for item in stories:
        story = _fields(item, {"id", "title", "scope", "acceptance_criteria", "verification", "depends_on"})
        identity = story["id"]
        if (
            not isinstance(identity, str)
            or not re.fullmatch(r"US-[0-9]{2,}", identity)
            or not any(c != "0" for c in identity[3:])
            or identity in dependencies
        ):
            raise FactoryError("Invalid plan: story IDs must be unique positive US-xx IDs")
        if not _narrative(story["title"]) or not _narrative(story["scope"]):
            raise FactoryError("Invalid plan: title and scope must be nonempty narrative text")
        for name in ("acceptance_criteria", "verification"):
            entries = story[name]
            if not isinstance(entries, list) or not entries or not all(_narrative(entry) for entry in entries):
                raise FactoryError("Invalid plan: criteria and verification must be nonempty narrative arrays")
        edges = story["depends_on"]
        if (
            not isinstance(edges, list)
            or not all(isinstance(edge, str) for edge in edges)
            or len(edges) != len(set(edges))
        ):
            raise FactoryError("Invalid plan: dependencies must be unique story IDs")
        dependencies[identity] = set(edges)
    for identity, edges in dependencies.items():
        if identity in edges or not edges <= dependencies.keys():
            raise FactoryError("Invalid plan: unknown or self dependency")
    remaining = {identity: set(edges) for identity, edges in dependencies.items()}
    while remaining:
        ready = {identity for identity, edges in remaining.items() if not edges}
        if not ready:
            raise FactoryError("Invalid plan: dependency cycle")
        remaining = {identity: edges - ready for identity, edges in remaining.items() if identity not in ready}


# Read strict UTF-8 JSON and validate it locally, reporting safe diagnostics on failure.
def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a local ticket plan")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--plan", type=Path, required=True)
    publication = commands.add_parser("publish")
    publication.add_argument("--plan", type=Path, required=True)
    publication.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        text = args.plan.read_text(encoding="utf-8")
        data = json.loads(text, object_pairs_hook=_object, parse_constant=_constant)
        validate_plan(data)
        if args.command == "publish":
            from software_factory.planning_publish import publish

            publish(data, args.dry_run)
            return 0
    except OSError, UnicodeError, ValueError, RecursionError:
        print("Cannot read plan: provide a readable, valid UTF-8 JSON file without duplicate keys", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Plan validation interrupted", file=sys.stderr)
        return 130
    except FactoryError as error:
        print(str(error), file=sys.stderr)
        return 1
    print("Ticket plan is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
