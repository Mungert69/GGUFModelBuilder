#!/usr/bin/env python3
import argparse
from tqdm import tqdm
from model_converter import ModelConverter  # This already contains Redis functionality

class MoeStatusUpdater:
    def __init__(self):
        self.converter = ModelConverter()
        
    def update_all_models(self, force_update=False):
        """Enhanced version with detailed logging"""
        catalog = self.converter.model_catalog.load_catalog()
        stats = {
            'total': 0,
            'already_correct': 0,
            'updated': 0,
            'converted_skipped': 0,
            'errors': 0,
            'moe_detected': 0
        }
        
        print(f"Checking {len(catalog)} models...\n")
        
        for model_id, model_data in catalog.items():
            stats['total'] += 1
            try:
                current_moe = model_data.get("is_moe", False)
                actual_moe = self.converter.check_moe_from_config(model_id)
                
                if actual_moe:
                    stats['moe_detected'] += 1
                    print(f"🔍 {model_id}: README indicates MoE")
                
                if current_moe != actual_moe:
                    if not force_update and model_data.get("converted", False):
                        stats['converted_skipped'] += 1
                        print(f"⏩ {model_id}: Skipping (already converted)")
                        continue
                        
                    if self.converter.model_catalog.update_model_field(
                        model_id,
                        "is_moe",
                        actual_moe
                    ):
                        stats['updated'] += 1
                        print(f"✅ {model_id}: Updated MoE={actual_moe}")
                    else:
                        print(f"❌ {model_id}: Failed to update")
                        stats['errors'] += 1
                else:
                    stats['already_correct'] += 1
                    print(f"☑ {model_id}: Already correct (MoE={actual_moe})")
                    
            except Exception as e:
                stats['errors'] += 1
                print(f"⚠ {model_id}: Error - {str(e)}")
        
        print("\n📊 Statistics:")
        print(f"Total models checked: {stats['total']}")
        print(f"Models with MoE indicators: {stats['moe_detected']}")
        print(f"Already correct: {stats['already_correct']}")
        print(f"Successfully updated: {stats['updated']}")
        print(f"Skipped (converted models): {stats['converted_skipped']}")
        print(f"Errors: {stats['errors']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update MoE status in Redis catalog")
    parser.add_argument("--all", action="store_true", help="Check all models in catalog")
    parser.add_argument("--force", action="store_true", help="Force update even on converted models")
    parser.add_argument("--model", type=str, help="Specific model ID to check")
    
    args = parser.parse_args()
    updater = MoeStatusUpdater()
    
    if args.all:
        updater.update_all_models(force_update=args.force)
    elif args.model:
        updater.update_specific_model(args.model)
    else:
        print("Please specify either --all or --model MODEL_ID")
        print("Example: python update_moe_status.py --all")
        print("Or: python update_moe_status.py --model Qwen/Qwen3-30B-A3B")
