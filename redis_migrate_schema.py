from model_converter import ModelConverter
import json

def migrate_schema():
    converter = ModelConverter()
    catalog = converter.model_catalog.load_catalog()
    
    migrated = 0
    failed = 0
    
    for model_id, model_data in catalog.items():
        if "is_moe" not in model_data:
            print(f"Migrating {model_id}...")
            model_data["is_moe"] = False  # Default value
            
            # Try normal update first
            if converter.model_catalog.update_model_field(model_id, "is_moe", False):
                migrated += 1
            else:
                # Fallback method
                try:
                    converter.model_catalog.r.hset(
                        converter.model_catalog.catalog_key,
                        model_id,
                        json.dumps(model_data)
                    )
                    migrated += 1
                except Exception as e:
                    print(f"Failed to migrate {model_id}: {str(e)}")
                    failed += 1
    
    print(f"\nMigration complete. Success: {migrated}, Failed: {failed}")
    if failed > 0:
        print("Warning: Some models failed migration. You may need to handle them manually.")

if __name__ == "__main__":
    migrate_schema()
