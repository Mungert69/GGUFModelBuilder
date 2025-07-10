#!/usr/bin/env python3
"""
Add all your Hugging Face models that satisfy a name match to a collection.

Usage examples
--------------
# Case-insensitive 'startswith' (default):
python add_models_to_collection.py

# Case-sensitive 'contains' anywhere in name:
python add_models_to_collection.py --matchany
"""
from huggingface_hub import (
    HfApi, login, list_models, list_collections,
    create_collection, add_collection_item,
)
from dotenv import load_dotenv
import huggingface_hub as hfhub
import argparse, os, sys, time

# ───────────────────────── 0 · CLI flags ────────────────────────────────
cli = argparse.ArgumentParser(description="Populate a HF collection with models.")
cli.add_argument("--matchany", action="store_true",
                 help="Match PREFIX anywhere in model name (case-sensitive). "
                      "Default: match only at the start (case-insensitive).")
args = cli.parse_args()

# ───────────────────────── 1 · Authenticate ─────────────────────────────
load_dotenv()
token = os.getenv("HF_API_TOKEN")
if not token:
    sys.exit("❌  HF_API_TOKEN not set (env or .env)")
login(token=token)                          # stores token
api = HfApi()
print(f"📦 huggingface_hub {hfhub.__version__}")

# ───────────────────────── 2 · Prompt user ──────────────────────────────
user   = input("Your HF username (case-sensitive): ").strip()
title  = input("Collection display title: ").strip()
prefix = input("Model name prefix to include: ").strip()

# ───────────────────────── 3 · Ensure collection ────────────────────────
coll = next((c for c in list_collections(owner=user) if c.title == title), None)
if coll is None:
    print("🆕  Creating collection …")
    coll = create_collection(
        title=title,
        description=f"Models that match '{prefix}' "
                    f"{'anywhere' if args.matchany else 'at start'}",
        private=False,
        exists_ok=True
    )
    print(f"✅  Created: {coll.slug}")
else:
    print(f"✅  Using existing collection: {coll.slug}")

# ───────────────────────── 4 · Gather models ────────────────────────────
def model_matches(model_id: str) -> bool:
    # remove "user/" prefix for matching
    short = model_id.split("/", 1)[1]
    if args.matchany:
        return prefix in short               # case-sensitive substring
    return short.lower().startswith(prefix.lower())

models = [m.id for m in list_models(author=user) if model_matches(m.id)]
if not models:
    sys.exit("❌  No models matched the given criteria.")

print(f"🔍  {len(models)} model(s) match:")
for m in models: print(" •", m)

# ───────────────────────── 5 · Add items ────────────────────────────────
for i, mid in enumerate(models, 1):
    print(f"[{i}/{len(models)}] adding {mid.ljust(50)}", end="")
    try:
        add_collection_item(
            collection_slug=coll.slug,
            item_id=mid,
            item_type="model",
            exists_ok=True
        )
        print(" ✓")
    except Exception as e:
        print(" ✗", e)
    time.sleep(0.4)

print("\n🎉  Completed. View at:", coll.url)
