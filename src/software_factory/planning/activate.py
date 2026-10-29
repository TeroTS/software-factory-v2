# Queue a published backlog explicitly without bypassing runner eligibility checks.
import sys

from software_factory.github import GitHub
from software_factory.planning.publish import existing, issue_number, operator
from software_factory.process import Commands, FactoryError


# Confirm every issue before writing labels; stop and report any uncertain write without retrying.
def activate(plan: dict) -> None:
    if plan["source"]["commit"] is None:
        raise FactoryError("Activation requires a full committed source revision")
    gh = GitHub(plan["repository"], Commands())
    login, repository = operator(gh, plan)
    print(f"Authenticated GitHub login: {login}; destination: {repository}", flush=True)
    found = existing(gh, plan)
    tickets = []
    for story in plan["stories"]:
        key = f"{plan['spec_id']}/{story['id']}"
        issue = found.get(key)
        if issue is None:
            raise FactoryError(f"Published ticket {key} not found; inspect repository issues")
        tickets.append((issue_number(issue, plan["repository"]), key, issue))
    if len({number for number, _, _ in tickets}) != len(tickets):
        raise FactoryError("Multiple planned stories map to one issue; inspect repository issues")
    for number, key, issue in sorted(tickets):
        if any(label["name"] == "agent:implement" for label in issue["labels"]):
            print(f"{key}: already queued #{number} {issue['html_url']}", flush=True)
            continue
        try:
            labels = gh.items(gh.api(f"issues/{number}/labels", method="POST", payload={"labels": ["agent:implement"]}))
            if any(not isinstance(label.get("name"), str) for label in labels):
                raise FactoryError("Label write not confirmed")
            names = {label["name"] for label in labels}
            if "agent:implement" not in names or not {label["name"] for label in issue["labels"]} <= names:
                raise FactoryError("Label write not confirmed")
        except (FactoryError, KeyboardInterrupt) as error:
            print(f"{key}: uncertain label write for #{number}; operator inspection required", file=sys.stderr)
            if isinstance(error, KeyboardInterrupt):
                raise
            raise FactoryError("Activation stopped; inspect the uncertain label write before retrying") from None
        print(f"{key}: queued #{number} {issue['html_url']}", flush=True)
