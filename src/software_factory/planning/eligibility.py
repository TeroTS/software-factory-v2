# Validate generated-ticket dependency graphs and merged closing PR evidence before a runner claims an issue.
import json
import re

from software_factory.github import GitHub
from software_factory.planning.publish import OPENER, metadata
from software_factory.process import FactoryError


# Return whether the checked issue is eligible; malformed graphs and lookup failures raise safe errors.
def eligible(github: GitHub, issue: dict) -> bool:
    current = metadata(issue, github.repository)
    if current is None:
        return True
    issues = github.items(github.api("issues?state=all&per_page=100", pages=True), pages=True)
    by_story = {}
    for candidate in issues:
        if "pull_request" in candidate:
            continue
        if candidate.get("number") == issue["number"]:
            candidate = issue
        try:
            data = metadata(candidate, github.repository)
        except FactoryError:
            # Invalid candidates with a readable identity still block that identity, not unrelated work.
            body = candidate.get("body")
            match = re.search(re.escape(OPENER) + r"\n([^\n]+)", body) if isinstance(body, str) else None
            try:
                raw = json.loads(match.group(1)) if match else None
                if isinstance(raw, dict) and raw.get("spec_id") == current["spec_id"]:
                    identity = raw.get("story_id")
                    if isinstance(identity, str):
                        by_story.setdefault(identity, []).append(None)
            except ValueError, RecursionError:
                pass
            continue
        if data is None or data["spec_id"] != current["spec_id"]:
            continue
        number = candidate.get("number")
        if type(number) is not int or number <= 0:
            raise FactoryError("Invalid generated issue number; inspect repository issues")
        by_story.setdefault(data["story_id"], []).append((number, data))
    if current["story_id"] not in by_story:
        raise FactoryError("Generated issue not found during dependency lookup; inspect repository issues")
    visited, active = set(), set()
    stack = [(current["story_id"], False)]
    while stack:
        identity, leaving = stack.pop()
        if leaving:
            active.remove(identity)
            visited.add(identity)
            continue
        if identity in active:
            raise FactoryError("Generated ticket dependency cycle; inspect planning metadata")
        if identity in visited:
            continue
        if identity not in by_story or len(by_story[identity]) != 1 or by_story[identity][0] is None:
            raise FactoryError(
                "Generated ticket prerequisite missing, invalid or duplicated; inspect planning metadata"
            )
        active.add(identity)
        stack.append((identity, True))
        stack.extend((dependency, False) for dependency in by_story[identity][0][1]["depends_on"])
    if not current["depends_on"]:
        return True
    branch = github.default_branch()
    for dependency in current["depends_on"]:
        prs = github.closing_prs(by_story[dependency][0][0])
        if not any(
            pr["merged"]
            and pr["baseRefName"] == branch
            and pr["baseRepository"]["nameWithOwner"].lower() == github.repository.lower()
            for pr in prs
        ):
            return False
    return True
