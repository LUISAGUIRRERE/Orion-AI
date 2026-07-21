#!/usr/bin/env python3
import argparse
import sys
import os
import subprocess
import re
from datetime import datetime

# ORION OS GitOps Automation Tool
# Designed by AutoClaw, Operations Engineer

def run_cmd(args, check=True):
    """Safely runs a command and returns the stdout."""
    try:
        res = subprocess.run(args, capture_output=True, text=True, check=check)
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command {' '.join(args)}:\nStdout: {e.stdout}\nStderr: {e.stderr}", file=sys.stderr)
        if check:
            sys.exit(e.returncode)
        return None

def sanitize_branch_name(name):
    """Sanitizes strings for safe git branch names."""
    name = name.lower()
    name = re.sub(r'[^a-z0-9\-_\s]', '', name)
    name = re.sub(r'\s+', '-', name)
    return name.strip('-')

def cmd_create_branch(args):
    """Creates a standardized feature or fix branch from an issue."""
    prefix = "feature" if args.type == "feature" else "fix"
    sanitized_title = sanitize_branch_name(args.title)
    branch_name = f"{prefix}/{args.issue_id}-{sanitized_title}"

    print(f"[*] Creating and switching to branch: {branch_name}")
    run_cmd(["git", "checkout", "-b", branch_name])
    print("[+] Branch created successfully.")

def cmd_commit(args):
    """Performs a commit adhering strictly to Conventional Commits."""
    valid_types = ["feat", "fix", "docs", "chore", "ops", "refactor", "test", "style"]
    if args.type not in valid_types:
        print(f"[-] Invalid commit type. Must be one of: {', '.join(valid_types)}", file=sys.stderr)
        sys.exit(1)

    scope_str = f"({args.scope})" if args.scope else ""
    commit_msg = f"{args.type}{scope_str}: {args.message}"

    print(f"[*] Staging all tracked changes...")
    run_cmd(["git", "add", "-u"])

    if args.all:
        print(f"[*] Staging all changes (including untracked)...")
        run_cmd(["git", "add", "-A"])

    # Check if there are changes to commit
    status = run_cmd(["git", "status", "--porcelain"])
    if not status:
        print("[-] No changes to commit.")
        sys.exit(0)

    print(f"[*] Committing changes: '{commit_msg}'")
    run_cmd(["git", "commit", "-m", commit_msg])
    print("[+] Changes committed successfully.")

def cmd_create_pr(args):
    """Generates PR metadata and automatically attempts PR creation."""
    print("[*] Generating Pull Request metadata...")
    current_branch = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if current_branch == "main":
        print("[-] Cannot create a PR from main branch.", file=sys.stderr)
        sys.exit(1)

    pr_template_path = ".github/PULL_REQUEST_TEMPLATE.md"
    template_content = ""
    if os.path.exists(pr_template_path):
        with open(pr_template_path, "r") as f:
            template_content = f.read()

    title = args.title or f"PR: {current_branch}"
    description = args.description or "Automated Pull Request from ORION GitOps Release Pipeline."

    # Format description using template if available
    if template_content:
        formatted_body = template_content.replace("<!--", "").replace("-->", "")
        formatted_body += f"\n\n### Description\n{description}\n"
    else:
        formatted_body = description

    print(f"[*] Base branch set to: {args.base}")
    print(f"[*] Push HEAD to remote origin...")
    # Safe push using run_cmd
    push_args = ["git", "push", "origin", "HEAD"]
    if args.force:
        push_args.append("--force")
    run_cmd(push_args, check=False)

    # Try using gh CLI if available
    gh_path = run_cmd(["which", "gh"], check=False)
    if gh_path:
        print("[*] gh CLI detected! Creating Pull Request on GitHub...")
        run_cmd(["gh", "pr", "create", "--title", title, "--body", formatted_body, "--base", args.base])
        print("[+] Pull Request created successfully via gh CLI.")
    else:
        # Save as artifact draft
        draft_path = "docs/PR_DRAFT.md"
        with open(draft_path, "w") as f:
            f.write(f"# PR Title: {title}\n\n# Target Base: {args.base}\n\n# Body:\n{formatted_body}\n")
        print(f"[+] gh CLI not found. Saved PR details to {draft_path} for manual/API review.")

def cmd_update_changelog(args):
    """Updates CHANGELOG.md with approved changes under Keep a Changelog convention."""
    changelog_path = "CHANGELOG.md"
    if not os.path.exists(changelog_path):
        print("[-] CHANGELOG.md not found in the root directory.", file=sys.stderr)
        sys.exit(1)

    version_header_pattern = rf"## \[{re.escape(args.version)}\]"

    with open(changelog_path, "r") as f:
        content = f.read()

    today = datetime.now().strftime("%Y-%m-%d")

    # Prepare insertion text
    category_header = f"### {args.category.capitalize()}"
    entry_line = f"- {args.message}"

    if re.search(version_header_pattern, content):
        # Version section already exists in CHANGELOG
        print(f"[*] Found existing version section for {args.version}")
        lines = content.splitlines()
        version_idx = -1
        next_version_idx = len(lines)

        for idx, line in enumerate(lines):
            if f"## [{args.version}]" in line:
                version_idx = idx
            elif version_idx != -1 and line.startswith("## "):
                next_version_idx = idx
                break

        version_lines = lines[version_idx:next_version_idx]
        category_idx = -1
        for idx, line in enumerate(version_lines):
            if category_header in line:
                category_idx = idx
                break

        if category_idx != -1:
            # Insert under existing category
            lines.insert(version_idx + category_idx + 1, entry_line)
        else:
            # Add category and then entry
            lines.insert(version_idx + 1, "")
            lines.insert(version_idx + 2, category_header)
            lines.insert(version_idx + 3, entry_line)

        new_content = "\n".join(lines) + "\n"
    else:
        # Version section does not exist, create it under the top description block
        print(f"[*] Creating new version section for {args.version}")
        new_version_block = f"\n## [{args.version}] - {today}\n\n{category_header}\n{entry_line}\n"

        # Insert below the introductory description (before the first version ## header)
        first_version_match = re.search(r"## \[", content)
        if first_version_match:
            insert_pos = first_version_match.start()
            new_content = content[:insert_pos] + new_version_block + content[insert_pos:]
        else:
            new_content = content + new_version_block

    with open(changelog_path, "w") as f:
        f.write(new_content)

    print(f"[+] CHANGELOG.md updated with entry under version {args.version} ({args.category}).")

def cmd_tag_release(args):
    """Automatically tags repository with a semantic version."""
    version = args.version.lstrip('v')
    tag_name = f"v{version}"

    # Check if tag already exists
    tags = run_cmd(["git", "tag"])
    if tag_name in tags.split():
        print(f"[-] Tag {tag_name} already exists.", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Creating annotated git tag: {tag_name}")
    run_cmd(["git", "tag", "-a", tag_name, "-m", f"Release version {tag_name}"])

    print(f"[*] Pushing tag {tag_name} to origin...")
    run_cmd(["git", "push", "origin", tag_name], check=False)
    print(f"[+] Tag {tag_name} created and pushed successfully.")

def cmd_merge(args):
    """Safely merges a branch into a target base branch (defaulting to main)."""
    current_branch = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    branch_to_merge = args.branch or current_branch

    if branch_to_merge == args.base:
        print(f"[-] Cannot merge branch into itself ({args.base}).", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Checking out base branch: {args.base}")
    run_cmd(["git", "checkout", args.base])

    print(f"[*] Merging branch '{branch_to_merge}' into '{args.base}' with '--no-ff' (for reversibility)...")
    run_cmd(["git", "merge", branch_to_merge, "--no-ff", "-m", f"merge: integrate {branch_to_merge} into {args.base}"])

    print(f"[*] Pushing merged base branch to origin...")
    run_cmd(["git", "push", "origin", args.base], check=False)

    print(f"[+] Successfully merged '{branch_to_merge}' into '{args.base}'.")

def cmd_approve(args):
    """Combined approval action: updates CHANGELOG, merges branch, and tags release."""
    print(f"[*] Running full approval pipeline for branch '{args.branch}'...")

    # 1. Update changelog
    cmd_update_changelog(args)

    # Commit CHANGELOG update
    run_cmd(["git", "add", "CHANGELOG.md"])
    run_cmd(["git", "commit", "-m", f"docs: update CHANGELOG.md for release v{args.version}"], check=False)

    # 2. Merge branch
    cmd_merge(args)

    # 3. Tag Release
    cmd_tag_release(args)

    print("[+] Combined approval pipeline completed successfully.")

def main():
    parser = argparse.ArgumentParser(description="ORION OS GitOps Automation Engine (AutoClaw)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-branch
    p_branch = subparsers.add_parser("create-branch", help="Create issue-aligned branch")
    p_branch.add_argument("--issue-id", required=True, help="Issue identifier (e.g. 42)")
    p_branch.add_argument("--title", required=True, help="Short descriptive title")
    p_branch.add_argument("--type", choices=["feature", "fix"], default="feature", help="Branch type prefix")
    p_branch.set_defaults(func=cmd_create_branch)

    # commit
    p_commit = subparsers.add_parser("commit", help="Commit changes following Conventional Commits")
    p_commit.add_argument("--type", required=True, help="Commit type (feat, fix, docs, chore, ops, etc.)")
    p_commit.add_argument("--scope", help="Optional scope")
    p_commit.add_argument("--message", required=True, help="Commit message")
    p_commit.add_argument("-a", "--all", action="store_true", help="Include untracked files (git add -A)")
    p_commit.set_defaults(func=cmd_commit)

    # create-pr
    p_pr = subparsers.add_parser("create-pr", help="Automate PR creation")
    p_pr.add_argument("--title", help="PR title")
    p_pr.add_argument("--description", help="Descriptive PR text")
    p_pr.add_argument("--base", default="main", help="Target branch for PR")
    p_pr.add_argument("-f", "--force", action="store_true", help="Force push branch to remote")
    p_pr.set_defaults(func=cmd_create_pr)

    # update-changelog
    p_changelog = subparsers.add_parser("update-changelog", help="Update CHANGELOG.md")
    p_changelog.add_argument("--version", required=True, help="Target release version")
    p_changelog.add_argument("--category", choices=["added", "changed", "deprecated", "removed", "fixed", "security"], required=True, help="Change category")
    p_changelog.add_argument("--message", required=True, help="Descriptive entry")
    p_changelog.set_defaults(func=cmd_update_changelog)

    # tag-release
    p_tag = subparsers.add_parser("tag-release", help="Tag repository version")
    p_tag.add_argument("--version", required=True, help="Target release version")
    p_tag.set_defaults(func=cmd_tag_release)

    # merge
    p_merge = subparsers.add_parser("merge", help="Safely merge feature branch")
    p_merge.add_argument("--branch", help="Source branch to merge (defaults to current)")
    p_merge.add_argument("--base", default="main", help="Destination base branch")
    p_merge.set_defaults(func=cmd_merge)

    # approve (combined update-changelog + merge + tag-release)
    p_approve = subparsers.add_parser("approve", help="Combined full release pipeline approval")
    p_approve.add_argument("--branch", required=True, help="Source feature branch to integrate")
    p_approve.add_argument("--version", required=True, help="Target release version")
    p_approve.add_argument("--category", choices=["added", "changed", "deprecated", "removed", "fixed", "security"], default="added", help="Change category for changelog")
    p_approve.add_argument("--message", required=True, help="Change entry description for changelog")
    p_approve.add_argument("--base", default="main", help="Target base branch to merge into")
    p_approve.set_defaults(func=cmd_approve)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
