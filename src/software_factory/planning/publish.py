# Publish reviewed plans through the operator's gh identity without updating or queuing existing issues.
import base64
import binascii
import json
import re
import sys
from urllib.parse import quote

from software_factory.github import GitHub
from software_factory.planning import _constant, _object, _valid_story_id, _validate_dependencies, _validate_provenance
from software_factory.process import Commands, FactoryError

LABEL = "factory:generated"
OPENER = "<!-- software-factory:planning"


# Render the exact issue title and body, preserving plan order and escaping the metadata comment boundary.
def render(plan: dict, story: dict) -> tuple[str, str]:
    identity = f"{plan['spec_id']}/{story['id']}"
    metadata = {
        "version": 1,
        "repository": plan["repository"],
        "spec_id": plan["spec_id"],
        "story_id": story["id"],
        "source": plan["source"],
        "depends_on": story["depends_on"],
    }
    encoded = json.dumps(metadata, sort_keys=True).replace("<", r"\u003c").replace(">", r"\u003e")
    dependencies = "\n".join(f"- {plan['spec_id']}/{item}" for item in story["depends_on"]) or "- None."
    body = (
        f"## Story\n{identity}\n## Source\n{plan['repository']}:{plan['source']['path']} at "
        f"{plan['source']['commit']}\n## Scope\n{story['scope']}\n## Acceptance criteria\n"
        + "\n".join(f"- [ ] {item}" for item in story["acceptance_criteria"])
        + "\n## Verification\n"
        + "\n".join(f"- {item}" for item in story["verification"])
        + f"\n## Dependencies\n{dependencies}\n{OPENER}\n{encoded}\n-->\n"
    )
    return f"[{identity}] {story['title']}", body


# Verify the exact committed source and explicitly declared story graph before any writes.
def verify_source(gh: GitHub, plan: dict) -> None:
    source = plan["source"]
    commit = source["commit"]
    if commit is None:
        raise FactoryError("Publication requires a full committed source revision")
    result = gh.api(f"commits/{commit}")
    if not isinstance(result, dict) or result.get("sha") != commit:
        raise FactoryError("Cannot confirm source commit in destination repository")
    commit_data = result.get("commit")
    tree = commit_data.get("tree") if isinstance(commit_data, dict) else None
    tree_sha = tree.get("sha") if isinstance(tree, dict) else None
    parts = source["path"].split("/")
    for index, part in enumerate(parts):
        if not isinstance(tree_sha, str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", tree_sha):
            raise FactoryError("Cannot confirm source file in commit tree")
        tree = gh.api(f"git/trees/{tree_sha}")
        entries = tree.get("tree") if isinstance(tree, dict) and not tree.get("truncated", False) else None
        if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
            raise FactoryError("Cannot confirm source file in commit tree")
        matches = [entry for entry in entries if entry.get("path") == part]
        if len(matches) != 1:
            raise FactoryError("Cannot confirm source file in commit tree")
        entry = matches[0]
        if index == len(parts) - 1:
            if entry.get("type") != "blob" or entry.get("mode") not in {"100644", "100755"}:
                raise FactoryError("Source spec must be a regular file")
        elif entry.get("type") != "tree" or entry.get("mode") != "040000":
            raise FactoryError("Source spec path must contain only directories")
        tree_sha = entry.get("sha")
    result = gh.api(f"contents/{quote(source['path'], safe='/')}?ref={commit}")
    try:
        if not isinstance(result, dict) or result.get("type") != "file" or result.get("encoding") != "base64":
            raise ValueError
        text = base64.b64decode(re.sub(r"\s", "", result["content"]), validate=True).decode("utf-8")
    except KeyError, TypeError, ValueError, UnicodeError, binascii.Error:
        raise FactoryError("Cannot read committed source spec as a regular UTF-8 file") from None
    ids = re.findall(r"(?m)^Spec ID:\s*`?([a-z0-9]+(?:-[a-z0-9]+)*)`?\s*$", text)
    sections = re.split(r"(?m)^###\s+(US-[0-9]{2,}):[^\n]*\n", text)
    graph = {}
    for index in range(1, len(sections), 2):
        identity, section = sections[index : index + 2]
        declarations = re.findall(r"(?m)^Depends on:\s*(.*?)\s*$", section)
        if identity in graph or len(declarations) != 1:
            raise FactoryError("Source spec has ambiguous story dependencies")
        value = declarations[0].replace("`", "").strip().removesuffix(".")
        if value == "None":
            dependencies = []
        elif re.fullmatch(r"US-[0-9]{2,}(?:\s*,\s*US-[0-9]{2,})*", value):
            dependencies = re.split(r"\s*,\s*", value)
        else:
            raise FactoryError("Source spec has invalid dependency declarations")
        if len(set(dependencies)) != len(dependencies):
            raise FactoryError("Source spec has duplicate dependencies")
        graph[identity] = set(dependencies)
    expected = {story["id"]: set(story["depends_on"]) for story in plan["stories"]}
    if ids != [plan["spec_id"]] or graph != expected:
        raise FactoryError("Source spec identity or dependencies do not match the plan")


# Parse exactly one valid generated metadata block; malformed candidates always block publication.
def metadata(issue: dict, repository: str) -> dict | None:
    body, labels = issue.get("body"), issue.get("labels")
    if body is not None and not isinstance(body, str):
        raise FactoryError("Invalid issue body during reconciliation")
    if not isinstance(labels, list) or any(
        not isinstance(x, dict) or not isinstance(x.get("name"), str) for x in labels
    ):
        raise FactoryError("Invalid issue labels during reconciliation")
    body = body or ""
    generated = any(x["name"] == LABEL for x in labels) or OPENER in body
    if not generated:
        return None
    match = re.search(re.escape(OPENER) + r"\n([^\n]+)\n-->", body)
    try:
        if body.count(OPENER) != 1 or not match:
            raise ValueError
        data = json.loads(match.group(1), object_pairs_hook=_object, parse_constant=_constant)
        if not isinstance(data, dict) or set(data) != {
            "version",
            "repository",
            "spec_id",
            "story_id",
            "source",
            "depends_on",
        }:
            raise ValueError
        _validate_provenance(data)
        deps = data["depends_on"]
        _validate_dependencies(deps)
        if (
            not _valid_story_id(data["story_id"])
            or not all(_valid_story_id(dependency) for dependency in deps)
            or data["story_id"] in deps
            or data["source"]["commit"] is None
            or data["repository"].lower() != repository.lower()
        ):
            raise ValueError
        return data
    except ValueError, TypeError, KeyError, RecursionError, FactoryError:
        raise FactoryError("Malformed generated issue metadata; inspect existing issues") from None


# Validate issue number and repository URL before treating any remote response as a confirmed mapping.
def issue_number(issue: object, repository: str) -> int:
    if not isinstance(issue, dict):
        raise FactoryError("Invalid issue response; operator inspection required")
    number = issue.get("number")
    url = issue.get("html_url")
    if (
        type(number) is not int
        or number <= 0
        or not isinstance(url, str)
        or not re.fullmatch(r"https://github\.com/" + re.escape(repository) + rf"/issues/{number}", url, re.I)
    ):
        raise FactoryError("Invalid issue identity; operator inspection required")
    return number


# Exhaustively inspect open and closed issues, rejecting ambiguous or malformed generated candidates.
def existing(gh: GitHub, plan: dict) -> dict[str, dict]:
    result = {}
    issues = gh.items(gh.api("issues?state=all&per_page=100", pages=True), pages=True)
    for issue in issues:
        if "pull_request" in issue:
            continue
        data = metadata(issue, plan["repository"])
        if data is None:
            continue
        issue_number(issue, plan["repository"])
        key = f"{data['spec_id']}/{data['story_id']}"
        if key in result:
            raise FactoryError("Duplicate generated story identity; operator inspection required")
        result[key] = issue
    return result


# Match all issue content while allowing only the committed revision to differ from the current plan.
def matches(issue: dict, plan: dict, story: dict) -> bool:
    data = metadata(issue, plan["repository"])
    if data is None:
        return False
    old = {**plan, "repository": data["repository"], "source": {**plan["source"], "commit": data["source"]["commit"]}}
    title, body = render(old, story)
    expected = metadata({"body": body, "labels": []}, plan["repository"])
    pattern = re.escape(OPENER) + r"\n[^\n]+\n-->"
    actual_prose = re.sub(pattern, OPENER, issue["body"], count=1)
    expected_prose = re.sub(pattern, OPENER, body, count=1)
    return issue.get("title") == title and actual_prose == expected_prose and data == expected


# Order prerequisites first, using story ID as the tie-breaker at each step.
def ordered(plan: dict) -> list[dict]:
    pending = {story["id"]: story for story in plan["stories"]}
    done = set()
    result = []
    while pending:
        identity = min(key for key, story in pending.items() if set(story["depends_on"]) <= done)
        result.append(pending.pop(identity))
        done.add(identity)
    return result


# Authenticate the operator and confirm the explicit destination before any writes.
def operator(gh: GitHub, plan: dict) -> tuple[str, str]:
    commands = gh.commands
    try:
        user = json.loads(
            commands.run(["gh", "api", "--hostname", "github.com", "user", "--method", "GET"], "GitHub identity")
        )
    except ValueError, RecursionError:
        raise FactoryError("Cannot confirm authenticated GitHub identity") from None
    login = user.get("login") if isinstance(user, dict) else None
    if not isinstance(login, str) or not re.fullmatch(r"[A-Za-z0-9-]+", login):
        raise FactoryError("Cannot confirm authenticated GitHub identity")
    repo = gh.api("")
    if (
        not isinstance(repo, dict)
        or not isinstance(repo.get("full_name"), str)
        or repo["full_name"].lower() != plan["repository"].lower()
    ):
        raise FactoryError("Cannot confirm destination repository")
    return login, repo["full_name"]


# Validate remote provenance and all conflicts before creating any issues.
def publish(plan: dict, dry_run: bool) -> None:
    gh = GitHub(plan["repository"], Commands())
    login, repository = operator(gh, plan)
    verify_source(gh, plan)
    stories = ordered(plan)
    for story in stories:
        _, body = render(plan, story)
        try:
            metadata({"body": body, "labels": []}, plan["repository"])
        except FactoryError:
            raise FactoryError(
                "Source path cannot be represented safely in the issue template; inspect the plan"
            ) from None
    if dry_run:
        for story in stories:
            title, body = render(plan, story)
            print(f"Title: {title}\nLabels: {LABEL}\n{body}")
        return
    print(f"Authenticated GitHub login: {login}; destination: {repository}", flush=True)
    found = existing(gh, plan)
    for story in stories:
        key = f"{plan['spec_id']}/{story['id']}"
        if key in found and not matches(found[key], plan, story):
            raise FactoryError(f"Conflict for {key}; inspect the existing issue")
    labels = gh.items(gh.api("labels?per_page=100", pages=True), pages=True)
    if any(not isinstance(label.get("name"), str) for label in labels):
        raise FactoryError("GitHub returned invalid repository labels")
    if not any(label["name"] == LABEL for label in labels):
        try:
            label = gh.api("labels", method="POST", payload={"name": LABEL})
            if not isinstance(label, dict) or label.get("name") != LABEL:
                raise FactoryError("label creation not confirmed")
        except (FactoryError, KeyboardInterrupt) as error:
            print("Generated label creation uncertain; operator inspection required", file=sys.stderr)
            if isinstance(error, KeyboardInterrupt):
                raise
            raise FactoryError("Publication stopped; inspect the uncertain label write") from None
    for story in stories:
        key = f"{plan['spec_id']}/{story['id']}"
        if key in found:
            issue = found[key]
            print(f"{key}: existing #{issue_number(issue, plan['repository'])} {issue['html_url']}", flush=True)
            continue
        title, body = render(plan, story)
        try:
            issue = gh.api("issues", method="POST", payload={"title": title, "body": body, "labels": [LABEL]})
            number = issue_number(issue, plan["repository"])
            if not matches(issue, plan, story) or not any(x["name"] == LABEL for x in issue["labels"]):
                raise FactoryError("issue content not confirmed")
        except (FactoryError, KeyboardInterrupt) as error:
            try:
                reconciled = existing(gh, plan).get(key)
                if (
                    reconciled
                    and matches(reconciled, plan, story)
                    and any(label["name"] == LABEL for label in reconciled["labels"])
                ):
                    print(
                        f"{key}: reconciled #{issue_number(reconciled, plan['repository'])} {reconciled['html_url']}",
                        flush=True,
                    )
            except FactoryError, KeyboardInterrupt:
                pass
            print(f"{key}: uncertain issue creation; operator inspection required", file=sys.stderr)
            if isinstance(error, KeyboardInterrupt):
                raise
            raise FactoryError("Publication stopped; inspect the uncertain write before retrying") from None
        print(f"{key}: created #{number} {issue['html_url']}", flush=True)
