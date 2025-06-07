
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'model-converter')))
from model_converter import ModelConverter
from make_files import get_model_size

def recalculate_all_model_sizes():
    converter = ModelConverter()
    catalog = converter.load_catalog()
    updated = 0

    for model_id, entry in catalog.items():
        print(f"\n[Recalculate] Processing {model_id}...")

        # Try config first
        parameters = entry.get('parameters', None)
        if parameters is not None and parameters != -1 and parameters != 0:
            print(f" - Existing parameters: {parameters} (skipping recalculation)")
            continue

        # Try get_model_size (local)
        base_name = model_id.split('/')[-1]
        parameters = get_model_size(base_name)
        if parameters is None or parameters == 0 or parameters == -1:
            # Try file size estimation
            total_size = converter.get_file_sizes(model_id)
            if total_size > 0:
                parameters = converter.estimate_parameters(total_size)
            else:
                parameters = -1

        print(f" - New parameters: {parameters}")
        converter.model_catalog.update_model_field(model_id, "parameters", parameters)
        updated += 1

    print(f"\n[Recalculate] Updated parameters for {updated} models.")

if __name__ == "__main__":
    recalculate_all_model_sizes()

