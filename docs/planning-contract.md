# Planning identity contract

A generated ticket's identity is its repository, spec ID and story ID in planning metadata;
titles and issue numbers are not identities. Publication and activation inspect open issues only.
They reject duplicate or malformed open generated tickets instead of selecting one.
Closing a ticket permits a subsequent publication to create a new ticket for that story.

For runner eligibility, a unique open ticket takes precedence over closed tickets with the same
identity. When no open ticket exists, a unique closed ticket can supply prerequisite evidence;
multiple candidates at the selected state or malformed selected metadata block the issue run.
Prerequisites still require a closing PR merged into the target default branch.
A missing or invalid issue state is an error. Inspect uncertain writes; never blindly retry them.
