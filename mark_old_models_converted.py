import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from redis_utils import init_redis_catalog

load_dotenv()

def main():
    REDIS_HOST = os.getenv("REDIS_HOST", "redis.readyforquantum.com")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "46379"))
    REDIS_USER = os.getenv("REDIS_USER", "admin")
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

    catalog = init_redis_catalog(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        user=REDIS_USER,
        ssl=True
    )

    all_models = catalog.load_catalog()
    now = datetime.now()
    cutoff = now - timedelta(days=30)
    updated = 0
    total_with_added = 0
    total_old = 0
    already_converted = 0

    print(f"Loaded {len(all_models)} models from catalog.")
    print(f"Today's date: {now}")
    print(f"Cutoff date (models added before this are considered old): {cutoff}")

    added_dates = []
    old_models = []
    for model_id, entry in all_models.items():
        added_str = entry.get("added", "")
        converted = entry.get("converted", False)
        if added_str:
            total_with_added += 1
            try:
                added_date = datetime.fromisoformat(added_str)
                added_dates.append(added_date)
            except Exception:
                print(f"Skipping {model_id}: could not parse date '{added_str}'")
                continue
            if added_date < cutoff:
                total_old += 1
                old_models.append((model_id, added_str, converted))
                print(f"{model_id}: added={added_str}, converted={converted}")
                if not converted:
                    print(f"Marking {model_id} as converted (added: {added_str})")
                    if catalog.update_model_field(model_id, "converted", True):
                        updated += 1
                else:
                    already_converted += 1

    print(f"\nCutoff date for conversion: {cutoff}")
    print(f"Models older than cutoff ({total_old}):")
    for model_id, added_str, converted in old_models:
        print(f"  {model_id}: added={added_str}, converted={converted}")

    print(f"\nDone. {updated} models updated.")
    print(f"{already_converted} models were already converted and older than 1 month.")
    print(f"{total_old} models are older than 1 month in total.")
    print(f"{total_with_added} models have an 'added' date.")
    print(f"{len(all_models)} models in total.")

    # Print summary of added dates
    if added_dates:
        earliest = min(added_dates)
        latest = max(added_dates)
        print(f"Earliest 'added' date: {earliest}")
        print(f"Latest 'added' date: {latest}")

        # Count models per week
        from collections import Counter
        week_counts = Counter(dt.strftime("%Y-%W") for dt in added_dates)
        print("\nModels added per week:")
        for week, count in sorted(week_counts.items()):
            print(f"  Week {week}: {count} models")
    else:
        print("No valid 'added' dates found.")

if __name__ == "__main__":
    main()
