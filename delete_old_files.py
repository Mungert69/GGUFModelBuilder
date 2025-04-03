from huggingface_hub import HfApi, HfFileSystem, login
from dotenv import load_dotenv
import os
import logging
from datetime import datetime, timezone, timedelta
import argparse

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load the .env file
load_dotenv()

# Read the API token from the .env file
api_token = os.getenv("HF_API_TOKEN")
if not api_token:
    logger.error("Hugging Face API token not found in .env file.")
    exit()

# Authenticate with the Hugging Face Hub
try:
    login(token=api_token)
    logger.info("Authentication successful.")
except Exception as e:
    logger.error(f"Authentication failed: {e}")
    exit()

# Initialize API and File System
api = HfApi()
fs = HfFileSystem()

def parse_arguments():
    parser = argparse.ArgumentParser(description='Delete old IQ1 files from Hugging Face repositories.')
    parser.add_argument('--dry-run', action='store_true', help='Run in dry mode without making any changes')
    parser.add_argument('--days', type=int, default=7, help='Number of days to consider a file as old (default: 7)')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--skip-files-without-date', action='store_true', help='Skip files that have no last modified date available')
    return parser.parse_args()

def is_file_older_than_days(file_path, days=7):
    """Check if a file is older than the specified number of days."""
    try:
        last_modified = fs.modified(file_path)
        if last_modified.tzinfo is None:
            last_modified = last_modified.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last_modified) > timedelta(days=days)
    except Exception as e:
        logger.error(f"Error retrieving modified date for {file_path}: {e}")
        return False

def process_iq_files(repo_id, dry_run=True, days=7, require_confirmation=True, debug=False, skip_files_without_date=False):
    try:
        logger.info(f"\nProcessing repository: {repo_id}")
        repo_files = list(api.list_repo_tree(repo_id=repo_id, recursive=True))
        logger.debug(f"Found {len(repo_files)} files in repository")
        
        files_to_process = []
        for file in repo_files:
            file_path = f"{repo_id}/{file.path}"
            if "iq1_s" in file.path.lower() or "iq1_m" in file.path.lower():
                if is_file_older_than_days(file_path, days):
                    files_to_process.append(file.path)
        
        if not files_to_process:
            logger.info(f"No matching files found in {repo_id}")
            return False, 0

        if require_confirmation:
            print(f"\nFound {len(files_to_process)} files to {'delete' if not dry_run else 'process'} in {repo_id}:")
            for file in files_to_process:
                print(f"- {file}")
            confirm = input(f"\nProceed? (y/n): ").lower()
            if confirm != 'y':
                logger.info("Operation cancelled by user")
                return False, 0

        processed_count = 0
        for file_path in files_to_process:
            try:
                if dry_run:
                    logger.info(f"[DRY RUN] Would delete {file_path} from {repo_id}")
                else:
                    api.delete_file(
                        path_in_repo=file_path,
                        repo_id=repo_id,
                        token=api_token,
                        commit_message=f"Removing old iq1 file: {file_path}"
                    )
                    logger.info(f"Deleted {file_path} from {repo_id}")
                processed_count += 1
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}")

        return True, processed_count
    except Exception as e:
        logger.error(f"Error processing {repo_id}: {e}", exc_info=True)
        return False, 0

def main():
    args = parse_arguments()
    if args.debug:
        logger.setLevel(logging.DEBUG)
    if args.dry_run:
        logger.info("\nRunning in DRY RUN mode - no files will be deleted\n")
    
    repos = list(api.list_models(author="Mungert"))
    logger.info(f"Found {len(repos)} repositories to check")
    logger.info(f"Looking for files older than {args.days} days")
    
    confirmed = False
    total_processed = 0
    for repo in repos:
        success, count = process_iq_files(
            repo.id, 
            dry_run=args.dry_run,
            days=args.days,
            require_confirmation=not confirmed,
            debug=args.debug,
            skip_files_without_date=args.skip_files_without_date
        )
        total_processed += count
        if success and not confirmed:
            confirmed = True
            logger.info(f"\nConfirmation received. {'Processing' if args.dry_run else 'Deleting'} files from remaining models automatically...")
            continue
        if confirmed and not success:
            logger.info(f"⏩ No matching files in {repo.id} - skipping")
    
    action = "processed (dry run)" if args.dry_run else "deleted"
    logger.info(f"\nOperation complete! Successfully {action} {total_processed} files across all repositories.")

if __name__ == "__main__":
    main()

