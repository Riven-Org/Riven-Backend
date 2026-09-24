#!/usr/bin/env python3
"""PreToolUse guard for Riven repos. Exit 2 blocks the tool call and shows the reason to Claude.

Rules:
- No force push, no pushing to main, no rewriting or deleting main.
- No bypassing branch protection or git hooks.
- Claude pushes branches; the user opens pull requests.
- Free plans only: no private visibility, Codespaces, larger runners, or licensed actions.
- Generated ticket files are read-only.
"""

import json
import re
import subprocess
import sys

STANDARD_RUNNERS = re.compile(r"^(ubuntu|windows|macos)-(latest|\d+(\.\d+)?)$")
PAID_ACTIONS = ("gitleaks/gitleaks-action",)
PROTECTION_CHANGE = "Changing branch protection or rulesets is not allowed. Ask the user."

BASH_RULES: list[tuple[str, str]] = [
    (
        r"\bgit\s+push\b[^|;&]*(\s-f\b|\s--force\b|\s--force-with-lease\b|\s--force-if-includes\b)",
        "Force push is not allowed. Merge origin/main into the branch and push a new commit.",
    ),
    (r"\bgit\s+push\b[^|;&]*\s\+\S+", "Force push via '+refspec' is not allowed."),
    (
        r"\bgit\s+push\b[^|;&]*\s(\S+:)?(refs/heads/)?main(?=$|\s|[;&|])",
        "Pushing to main is not allowed. Push a feature branch; the user opens the PR.",
    ),
    (
        r"\bgit\s+push\b[^|;&]*\s--(delete|mirror)\b",
        "Deleting remote branches or mirror-pushing is not allowed.",
    ),
    (
        r"\bgit\s+(commit|push|merge|rebase)\b[^|;&]*\s--no-verify\b",
        "Skipping git hooks (--no-verify) is not allowed.",
    ),
    (r"\bgit\s+branch\s+(-D|-d|--delete)\s+main(?=$|\s|[;&|])", "Deleting main is not allowed."),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard discards work. Ask the user first."),
    (r"\bgh\s+pr\s+create\b", "Claude does not open pull requests. Push the branch and report it."),
    (r"\bgh\s+pr\s+merge\b[^|;&]*\s--admin\b", "Merging with --admin bypasses branch protection."),
    (
        r"\bgh\s+repo\s+edit\b[^|;&]*--visibility",
        "Changing repo visibility is not allowed (private repos lose free protection and CI).",
    ),
    (r"\bgh\s+repo\s+(delete|archive)\b", "Deleting or archiving a repo is not allowed."),
    (r"\bgh\s+codespace\s+create\b", "Codespaces are billed to the org. Work locally."),
    (
        r"\bgh\s+api\b[^|;&]*(-X|--method)\s*(DELETE|PUT|PATCH|POST)\b[^|;&]*/(protection|rulesets)\b",
        PROTECTION_CHANGE,
    ),
    (
        r"\bgh\s+api\b[^|;&]*/(protection|rulesets)\b[^|;&]*(-X|--method)\s*(DELETE|PUT|PATCH|POST)\b",
        PROTECTION_CHANGE,
    ),
]
BARE_PUSH = re.compile(r"\bgit\s+push(\s+(-u|--set-upstream|origin|\s)*)?\s*($|[|;&])")


def block(reason: str) -> None:
    print(f"Blocked by Riven guardrails: {reason}", file=sys.stderr)
    sys.exit(2)


def current_branch(cwd: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", cwd, "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def check_bash(command: str, cwd: str) -> None:
    for pattern, reason in BASH_RULES:
        if re.search(pattern, command):
            block(reason)
    # A bare `git push` / `git push origin` pushes the current branch.
    if BARE_PUSH.search(command) and current_branch(cwd) == "main":
        block("You are on main; a bare 'git push' would push to main. Create a branch first.")


def check_write(path: str, content: str) -> None:
    if re.search(r"(^|/)docs/tickets/", path):
        block("docs/tickets is generated from the backlog. Don't edit it; flag the problem.")
    if re.search(r"(^|/)\.github/workflows/", path):
        for action in PAID_ACTIONS:
            if action in content:
                block(f"{action} needs a paid license for org repos. Use the free CLI instead.")
        for runner in re.findall(r"runs-on:\s*\[?\s*([^\s\],#]+)", content):
            label = runner.strip("'\"")
            if "${{" not in label and not STANDARD_RUNNERS.match(label):
                block(f"Runner '{label}' is not a standard GitHub-hosted runner (larger = paid).")


def main() -> None:
    data = json.load(sys.stdin)
    tool = data.get("tool_name", "")
    params = data.get("tool_input", {}) or {}
    if tool == "Bash":
        check_bash(params.get("command", ""), data.get("cwd", "."))
    elif tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        content = params.get("content") or params.get("new_string") or ""
        for edit in params.get("edits", []) or []:
            content += "\n" + edit.get("new_string", "")
        check_write(params.get("file_path", ""), content)


if __name__ == "__main__":
    main()
