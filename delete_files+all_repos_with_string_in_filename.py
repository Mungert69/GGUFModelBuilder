import os
import argparse
from huggingface_hub import HfApi, login
from dotenv import load_dotenv

def main():
    parser = argparse.ArgumentParser(description="Delete files from all Hugging Face repos for a user that match any of the given substrings.")
    parser.add_argument(
        "--substring",
        nargs="+",
        required=True,
        help="One or more substrings to search for in file names (case-insensitive)"
    )
    parser.add_argument(
        "--exclude-substring",
        nargs="+",
        default=[],
        help="One or more substrings to exclude from deletion (case-insensitive)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted, but don't delete")
    parser.add_argument("--user", default=None, help="Hugging Face username (default: read from model-converter/username)")
    args = parser.parse_args()

    load_dotenv()
    HF_TOKEN = os.getenv("HF_API_TOKEN")
    if not HF_TOKEN:
        print("Error: HF_API_TOKEN not found in .env")
        return

    # Get username if not provided
    if args.user:
        username = args.user
    else:
        username_file = os.path.join(os.path.dirname(__file__), "model-converter/username")
        with open(username_file, "r") as f:
            username = f.read().strip()

    login(token=HF_TOKEN)
    api = HfApi()

    print(f"Fetching repos for user: {username}")
    repos = list(api.list_models(author=username))
    print(f"Found {len(repos)} repos.")

    substrings = [s.lower() for s in args.substring]
    exclude_substrings = [s.lower() for s in args.exclude_substring]
    total_deleted = 0

    for repo in repos:
        repo_id = repo.modelId
        try:
            files = api.list_repo_files(repo_id)
            to_delete = []
            for f in files:
                fname = f.lower()
                # Match if file contains any of the target substrings
                if any(sub in fname for sub in substrings):
                    # Skip if it contains any excluded substring
                    if any(excl in fname for excl in exclude_substrings):
                        continue
                    to_delete.append(f)
            if not to_delete:
                continue
            print(f"\nRepo: {repo_id}")
            for file in to_delete:
                print(f"  Found: {file}")
            if not args.dry_run:
                for file in to_delete:
                    try:
                        api.delete_file(
                            path_in_repo=file,
                            repo_id=repo_id,
                            token=HF_TOKEN,
                            commit_message=f"Delete file(s) containing {args.substring}"
                        )
                        print(f"  Deleted: {file}")
                        total_deleted += 1
                    except Exception as e:
                        print(f"  Failed to delete {file}: {e}")
            else:
                print("  (dry run, not deleting)")
        except Exception as e:
            print(f"Error processing {repo_id}: {e}")

    print(f"\nDone. {'Would have deleted' if args.dry_run else 'Deleted'} {total_deleted} files.")

if __name__ == "__main__":
    main()
