#!/usr/bin/env python3
"""
Super-squash the default branch across multiple Hugging Face repos to reclaim storage.

Usage:
  python hf_super_squash_all.py [--user USERNAME]
                                [--repo-type model|dataset|space]
                                [--include SUBSTR ...]
                                [--exclude SUBSTR ...]
                                [--message "commit message"]
                                [--dry-run]
                                [--yes]

Examples:
  # Squash all your model repos' default branches (interactive confirm)
  python hf_super_squash_all.py

  # Only repos containing "llama" but not "test", and auto-confirm
  python hf_super_squash_all.py --include llama --exclude test --yes

  # Datasets, with a custom message
  python hf_super_squash_all.py --repo-type dataset --message "Reclaim storage"
"""

import os
import sys
import argparse
from typing import Optional, List

from huggingface_hub import HfApi, login

def detect_default_branch(api: HfApi, repo_id: str, repo_type: str) -> str:
    """
    Try to detect default branch server-side; fall back to 'main'.
    """
    try:
        info = api.get_repo_info(repo_id=repo_id, repo_type=repo_type)
        # RepoInfo.default_branch exists on recent huggingface_hub; be defensive.
        default_branch = getattr(info, "default_branch", None)
        if not default_branch:
            # Some repos still default to "main" or "master"; try "main" first.
            return "main"
        return default_branch
    except Exception:
        return "main"

def should_process(name: str, include: List[str], exclude: List[str]) -> bool:
    n = name.lower()
    if include and not any(s in n for s in include):
        return False
    if exclude and any(s in n for s in exclude):
        return False
    return True

def main():
    p = argparse.ArgumentParser(description="Super-squash default branch across many HF repos.")
    p.add_argument("--user", default=None, help="HF username (defaults to token owner)")
    p.add_argument("--repo-type", default="model", choices=["model", "dataset", "space"], help="Type of repos to process")
    p.add_argument("--include", nargs="*", default=[], help="Process only repos whose name contains any of these substrings (case-insensitive)")
    p.add_argument("--exclude", nargs="*", default=[], help="Skip repos whose name contains any of these substrings (case-insensitive)")
    p.add_argument("--message", default="Super-squash history to reclaim storage", help="Commit message for the squash")
    p.add_argument("--dry-run", action="store_true", help="Show what would be done but do not execute")
    p.add_argument("--yes", action="store_true", help="Do not prompt for confirmation; proceed automatically")
    args = p.parse_args()

    token = os.getenv("HF_API_TOKEN")
    if not token:
        print("Error: HF_API_TOKEN not set in the environment.")
        sys.exit(1)

    login(token=token)
    api = HfApi(token=token)

    # Resolve username if not provided
    username = args.user
    if not username:
        try:
            # whoami + orgs is available via HfApi.whoami
            me = api.whoami()
            username = me.get("name") or me.get("fullname") or me.get("email") or ""
            if not username:
                raise RuntimeError("Could not resolve username from token (whoami empty).")
        except Exception as e:
            print(f"Error resolving username from token: {e}")
            sys.exit(1)

    print(f"Fetching {args.repo_type} repos for user/org: {username} ...")
    try:
        if args.repo_type == "model":
            items = list(api.list_models(author=username))
            # Each item has .modelId
            repo_ids = [it.modelId for it in items]
        elif args.repo_type == "dataset":
            items = list(api.list_datasets(author=username))
            repo_ids = [it.id for it in items]  # e.g., "user/dataset"
        else:  # space
            items = list(api.list_spaces(author=username))
            repo_ids = [it.id for it in items]
    except Exception as e:
        print(f"Error listing repositories: {e}")
        sys.exit(1)

    include = [s.lower() for s in args.include]
    exclude = [s.lower() for s in args.exclude]

    repo_ids = [r for r in repo_ids if should_process(r, include, exclude)]

    if not repo_ids:
        print("No repositories matched the filters.")
        return

    print(f"Matched {len(repo_ids)} repos.")
    if args.dry_run:
        for r in repo_ids:
            branch = detect_default_branch(api, r, args.repo_type)
            print(f"[DRY-RUN] Would super-squash {r} (branch: {branch}) with message: {args.message}")
        return

    # Confirm batch unless --yes
    if not args.yes:
        print("\nThis will PERMANENTLY rewrite history of the default branch for the repos above.")
        print("Old SHAs will be invalid; current HEAD snapshot remains intact.")
        proceed = input("Type 'yes' to proceed with ALL: ").strip().lower()
        if proceed != "yes":
            print("Aborted.")
            return

    successes = 0
    failures = 0

    for repo_id in repo_ids:
        branch = detect_default_branch(api, repo_id, args.repo_type)
        print(f"\nProcessing: {repo_id} (branch: {branch})")
        try:
            api.super_squash_history(
                repo_id=repo_id,
                branch=branch,
                commit_message=args.message,
                repo_type=args.repo_type,
            )
            print("  ✓ Super-squash completed.")
            successes += 1
        except Exception as e:
            print(f"  ✗ Error: {e}")
            failures += 1

    print(f"\nDone. Successful: {successes}  Failed: {failures}")
    print("Note: Storage metrics in Settings can take time to refresh.")

if __name__ == "__main__":
    main()

