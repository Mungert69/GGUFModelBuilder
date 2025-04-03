import json
import readline  # For better input handling
from redis_utils import init_redis_catalog
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
def import_models(catalog):
    """UI handler for model imports"""
    print("\n=== Import Models ===")
    file_path = input("Enter path to JSON file containing models: ")
    
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            models_to_import = data.get('models', [])
    except Exception as e:
        print(f"Error loading file: {e}")
        return
    
    if not models_to_import:
        print("No models found in the file!")
        return
    
    print(f"\nFound {len(models_to_import)} models in the file")
    result = catalog.import_models_from_list(models_to_import)
    
    print(f"\nImport completed:")
    print(f"- {result['added']} new models added")
    print(f"- {result['updated']} existing models updated")

def initialize_catalog():
    """Initialize Redis connection"""
    print("\n=== Redis Connection Setup ===")
    host = input("Redis host [redis.freenetworkmonitor.click]: ") or "redis.freenetworkmonitor.click"
    port = int(input("Redis port [46379]: ") or 46379)
    user = input("Redis user [admin]: ") or "admin"
    
    # Get password - try input first, then .env
    password_input = input("Redis password (leave empty to check .env): ")
    password = password_input if password_input else os.getenv("REDIS_PASSWORD")
    
    if not password:
        print("Warning: No password provided and REDIS_PASSWORD not found in .env file")
    
    ssl = input("Use SSL? [Y/n]: ").lower() in ('', 'y', 'yes')
    
    return init_redis_catalog(
        host=host,
        port=port,
        password=password,
        user=user,
        ssl=ssl
    )

def search_models(catalog):
    """Search models in catalog"""
    print("\n=== Search Models ===")
    search_term = input("Enter search term (leave empty for all): ")
    
    all_models = catalog.load_catalog()
    if not all_models:
        print("No models found in catalog!")
        return []
    
    matched_models = []
    for model_id, data in all_models.items():
        if not search_term or search_term.lower() in model_id.lower():
            matched_models.append((model_id, data))
    
    print(f"\nFound {len(matched_models)} models:")
    for i, (model_id, _) in enumerate(matched_models, 1):
        print(f"{i}. {model_id}")
    
    return matched_models

def edit_model(catalog, model_id):
    """Edit a model's data with proper type handling for all fields"""
    model_data = catalog.get_model(model_id)
    if not model_data:
        print(f"Model {model_id} not found!")
        return
    
    print(f"\n=== Editing {model_id} ===")
    
    def display_current_data():
        """Helper function to display current model data"""
        print("\nCurrent model data:")
        print(json.dumps(model_data, indent=2))
    
    display_current_data()
    
    # Define field type expectations
    FIELD_TYPES = {
        "added": str,
        "parameters": int,
        "has_config": bool,
        "converted": bool,
        "attempts": int,
        "last_attempt": str,
        "success_date": (str, type(None)),
        "error_log": list,
        "quantizations": list
    }
    
    def convert_value(value, target_type):
        """Convert input value to the expected type"""
        if value == "":
            return None
        
        if target_type == bool:
            if isinstance(value, str):
                return value.lower() in ('true', 't', 'yes', 'y', '1')
            return bool(value)
        
        try:
            if target_type in (str, type(None)):
                return str(value) if value else None
            elif target_type == int:
                return int(value)
            elif target_type == list:
                if isinstance(value, str):
                    return json.loads(value) if value else []
                return value if isinstance(value, list) else [value]
            return target_type(value)
        except (ValueError, TypeError, json.JSONDecodeError):
            print(f"Warning: Could not convert {value} to {target_type}")
            return None
    
    while True:
        print("\nAvailable fields:")
        for i, field in enumerate(model_data.keys(), 1):
            print(f"{i}. {field}")
        
        choice = input("\nChoose field to edit (number), 'a' to add new field, or 'q' to quit: ")
        
        if choice.lower() == 'q':
            break
            
        if choice.lower() == 'a':
            new_field = input("Enter new field name: ")
            if new_field in model_data:
                print("Field already exists!")
                continue
                
            new_value = input(f"Enter value for {new_field}: ")
            try:
                new_value = eval(new_value) if new_value else None
            except:
                pass
                
            model_data[new_field] = new_value
            if catalog.update_model_field(model_id, new_field, new_value):
                print("\nField added successfully!")
                display_current_data()
            else:
                print("Failed to add field!")
            continue
            
        try:
            field_num = int(choice) - 1
            fields = list(model_data.keys())
            if field_num < 0 or field_num >= len(fields):
                print("Invalid selection!")
                continue
                
            field = fields[field_num]
            current_value = model_data[field]
            expected_type = FIELD_TYPES.get(field, str)
            
            print(f"\nCurrent value of {field}: {current_value} ({type(current_value)})")
            print(f"Expected type: {expected_type.__name__ if not isinstance(expected_type, tuple) else ' or '.join(t.__name__ for t in expected_type)}")
            
            new_value = input(f"Enter new value (leave empty to cancel): ")
            if not new_value and field not in ["error_log", "quantizations"]:
                continue
                
            # Convert the input to the proper type
            converted_value = convert_value(new_value, expected_type)
            if converted_value is None and new_value != "":
                print(f"Invalid value for type {expected_type}")
                continue
            
            # Special handling for empty lists
            if field in ["error_log", "quantizations"] and new_value == "":
                converted_value = []
            
            # For all fields, use direct Redis update to ensure it works
            current_data = catalog.get_model(model_id)
            if current_data:
                current_data[field] = converted_value
                catalog.r.hset(catalog.catalog_key, model_id, json.dumps(current_data))
                model_data[field] = converted_value
                print("\nField updated successfully!")
                display_current_data()
            else:
                print("Failed to get current model data")
                    
        except ValueError:
            print("Please enter a valid number or command")

def delete_model(catalog, model_id):
    """Delete a model from catalog"""
    confirm = input(f"Are you sure you want to delete {model_id}? [y/N]: ").lower()
    if confirm != 'y':
        print("Deletion cancelled")
        return
    
    if catalog.r.hdel(catalog.catalog_key, model_id):
        print("Model deleted successfully")
    else:
        print("Model not found or deletion failed")

def main():
    catalog = initialize_catalog()
    
    while True:
        print("\n=== Main Menu ===")
        print("1. Search models")
        print("2. Edit a model by exact ID")
        print("3. Backup catalog to file")
        print("4. Restore catalog from file")
        print("5. Import models from JSON")
        print("6. Exit")
        
        choice = input("Choose an option: ")
        
        if choice == '1':
            matched_models = search_models(catalog)
            if not matched_models:
                continue
                
            model_choice = input("\nEnter model number to edit (or 'q' to cancel): ")
            if model_choice.lower() == 'q':
                continue
                
            try:
                model_num = int(model_choice) - 1
                if model_num < 0 or model_num >= len(matched_models):
                    print("Invalid selection!")
                    continue
                    
                model_id, _ = matched_models[model_num]
                edit_model(catalog, model_id)
            except ValueError:
                print("Please enter a valid number")
                
        elif choice == '2':
            model_id = input("\nEnter exact model ID to edit: ")
            edit_model(catalog, model_id)
            
        elif choice == '3':
            file_path = input("Enter backup file path: ")
            if catalog.backup_to_file(file_path):
                print("Backup successful!")
            else:
                print("Backup failed!")
                
        elif choice == '4':
            file_path = input("Enter restore file path: ")
            confirm = input("WARNING: This will overwrite current catalog. Continue? [y/N]: ").lower()
            if confirm == 'y':
                if catalog.initialize_from_file(file_path):
                    print("Restore successful!")
                else:
                    print("Restore failed!")
        elif choice == '5':
            import_models(catalog)
        elif choice == '6':
            print("Exiting...")
            break
            
        else:
            print("Invalid choice!")

if __name__ == "__main__":
    main()
