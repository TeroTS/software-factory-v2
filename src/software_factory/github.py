# Access the configured GitHub.com repository through host gh; keep task text in JSON stdin, not shell commands.
import json
import re
from urllib.parse import quote

from software_factory.process import Commands, FactoryError


# Own issue discovery, exact duplicate checks, status comments, and draft PR creation without durable local state.
class GitHub:
    # Bind the trusted repository name and command budget used by all requests.
    def __init__(self, repository: str, commands: Commands) -> None:
        self.repository = repository
        self.commands = commands

    # Decode gh API JSON; return sanitized errors instead of raw remote content or uncertain success.
    def api(self, path: str, *, payload: dict | None = None, method: str = "GET", pages: bool = False) -> object:
        args = [
            "gh",
            "api",
            "--hostname",
            "github.com",
            f"repos/{self.repository}" + (f"/{path}" if path else ""),
            "--method",
            method,
        ]
        if pages:
            args += ["--paginate", "--slurp"]
        if payload is not None:
            args += ["--input", "-"]
        output = self.commands.run(args, "GitHub " + method, input=None if payload is None else json.dumps(payload))
        try:
            return json.loads(output)
        except ValueError:
            raise FactoryError("GitHub returned invalid JSON; no operation result assumed") from None

    # Validate array/object framing and optionally flatten gh pagination; malformed responses fail closed.
    def items(self, data: object, *, pages: bool = False) -> list[dict]:
        if not isinstance(data, list):
            raise FactoryError("GitHub returned an invalid array response")
        if pages:
            if any(not isinstance(page, list) for page in data):
                raise FactoryError("GitHub returned invalid page framing")
            data = [item for page in data for item in page]
        if any(not isinstance(item, dict) for item in data):
            raise FactoryError("GitHub returned invalid array entries")
        return data

    # Discover every open labeled issue, excluding PRs; pagination never silently truncates the work list.
    def discover(self) -> list[int]:
        issues = self.items(self.api("issues?state=open&labels=agent%3Aimplement&per_page=100", pages=True), pages=True)
        numbers = []
        for issue in issues:
            if "pull_request" in issue:
                continue
            number = issue.get("number")
            if type(number) is not int or number <= 0:
                raise FactoryError("GitHub returned an invalid issue number")
            numbers.append(number)
        return numbers

    # Match PR identity by both head repository and branch, never body text or a prefix.
    def open_pr(self, number: int) -> str | None:
        query = quote(f"{self.repository.split('/')[0]}:factory/issue-{number}", safe="")
        prs = self.items(self.api(f"pulls?state=open&head={query}&per_page=100", pages=True), pages=True)
        for pr in prs:
            head = pr.get("head")
            if not isinstance(head, dict) or not isinstance(head.get("ref"), str):
                raise FactoryError("GitHub returned invalid PR head identity")
            repository = head.get("repo") or {}
            if not isinstance(repository, dict) or not isinstance(repository.get("full_name", ""), str):
                raise FactoryError("GitHub returned invalid PR head repository")
            if (
                repository.get("full_name", "").lower() == self.repository.lower()
                and head["ref"] == f"factory/issue-{number}"
            ):
                return self.pr_url(pr)
        return None

    # Query matching refs and compare the complete ref; failed reads must propagate instead of meaning absence.
    def branch_exists(self, number: int) -> bool:
        refs = self.items(self.api(f"git/matching-refs/heads/factory/issue-{number}"))
        if any(not isinstance(item.get("ref"), str) for item in refs):
            raise FactoryError("GitHub returned an invalid branch reference")
        return any(item["ref"] == f"refs/heads/factory/issue-{number}" for item in refs)

    # Remove the eligibility label and verify GitHub's returned remaining labels before executing or notifying.
    def remove_trigger(self, number: int) -> None:
        labels = self.items(self.api(f"issues/{number}/labels/agent%3Aimplement", method="DELETE"))
        if any(not isinstance(label.get("name"), str) for label in labels):
            raise FactoryError("GitHub returned invalid labels after trigger removal")
        if any(label["name"] == "agent:implement" for label in labels):
            raise FactoryError("GitHub label removal was not confirmed")

    # Capture only the current issue's title/body and identity; comments and linked content are never fetched.
    def snapshot(self, number: int) -> dict:
        issue = self.api(f"issues/{number}")
        if not isinstance(issue, dict) or not isinstance(issue.get("title"), str) or "body" not in issue:
            raise FactoryError("GitHub returned invalid issue snapshot")
        if issue["body"] is not None and not isinstance(issue["body"], str):
            raise FactoryError("GitHub returned invalid issue body")
        return {"number": number, "title": issue["title"], "body": issue["body"]}

    # Post a concise runner-owned status message via stdin, without interpolating content into a host shell.
    def comment(self, number: int, message: str) -> None:
        self.api(f"issues/{number}/comments", method="POST", payload={"body": message})

    # Discover the target default branch rather than assuming main or accepting a separate configuration policy.
    def default_branch(self) -> str:
        repository = self.api("")
        if (
            not isinstance(repository, dict)
            or not isinstance(repository.get("default_branch"), str)
            or not repository["default_branch"]
        ):
            raise FactoryError("GitHub returned an invalid default branch")
        return repository["default_branch"]

    # Create one draft PR from the known factory branch; uncertain failures are not automatically retried.
    def publish(self, number: int, title: str, base: str) -> str:
        pr = self.api(
            "pulls",
            method="POST",
            payload={
                "title": title,
                "head": f"factory/issue-{number}",
                "base": base,
                "body": f"Closes #{number}",
                "draft": True,
            },
        )
        return self.pr_url(pr)

    # Require the actual returned URL in this repository before reporting a successful PR link.
    def pr_url(self, pr: object) -> str:
        url = pr.get("html_url", "") if isinstance(pr, dict) else ""
        if not isinstance(url, str) or not re.fullmatch(
            r"https://github\.com/" + re.escape(self.repository) + r"/pull/[1-9]\d*", url, re.I
        ):
            raise FactoryError(
                "GitHub did not return a valid draft PR URL; publication outcome needs operator inspection"
            )
        return url
