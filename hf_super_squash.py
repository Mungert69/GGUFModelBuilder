#!/usr/bin/env python3
"""
Super-squash a Hugging Face repo branch to reclaim storage.

Usage:
  python super_squash_repo.py <repo_id> [--branch BRANCH] [--message "commit msg"] [--repo-type TYPE]

Examples:
  python super_squash_repo.py my-user/my-repo
  python super_squash_repo.py my-user/my-repo --branch main --message "Reclaim storage"
  python super_squash_repo.py my-user/my-dataset --repo-type dataset

Notes:
  - Requires HF_API_TOKEN in your environment with write perms.
  - This REWRITES HISTORY for the specified branch (destructive for old SHAs).
"""

import os
import sys
from huggingface_hub import HfApi

def parse_args(argv):
    if len(argv) < 2 or argv[1].startswith("-"):
        print(__doc__)
        sys.exit(1)

    repo_id = argv[1]
    branch = "main"
    commit_message = "Super-squash history to reclaim storage"
    repo_type = "model"  # use "dataset" or "space" if needed

    i = 2
    while i < len(argv):
        arg = argv[i]
        if arg == "--branch" and i + 1 < len(argv):
            branch = argv[i + 1]
            i += 2
        elif arg == "--message" and i + 1 < len(argv):
            commit_message = argv[i + 1]
            i += 2
        elif arg == "--repo-type" and i + 1 < len(argv):
            repo_type = argv[i + 1]
            if repo_type not in {"model", "dataset", "space"}:
                print("Error: --repo-type must be one of: model | dataset | space")
                sys.exit(1)
            i += 2
        else:
            print(f"Unknown or incomplete argument: {arg}\n")
            print(__doc__)
            sys.exit(1)

    return repo_id, branch, commit_message, repo_type

def main():
    repo_id, branch, commit_message, repo_type = parse_args(sys.argv)

    token = os.getenv("HF_API_TOKEN")
    if not token:
        print("Error: HF_API_TOKEN not set in environment.")
        sys.exit(1)

    api = HfApi(token=token)

    print(f"""
About to SUPER-SQUASH:
  repo:       {repo_id}
  repo_type:  {repo_type}
  branch:     {branch}
  message:    {commit_message}

This is DESTRUCTIVE for history on the target branch:
  • Old commits will be replaced by a single commit containing the current HEAD snapshot.
  • Old SHAs will no longer resolve.
  • Other branches/tags are unaffected.

Type 'yes' to proceed: """, end="", flush=True)

    confirm = sys.stdin.readline().strip().lower()
    if confirm != "yes":
        print("Aborted.")
        sys.exit(1)

    try:
        api.super_squash_history(
            repo_id=repo_id,
            branch=branch,
            commit_message=commit_message,
            repo_type=repo_type,
        )
        print("Super-squash completed. Storage metrics in Settings may take a little time to refresh.")
    except Exception as e:
        print(f"Error during super-squash: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

