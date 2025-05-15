import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
print("sys.path:", sys.path)
print("Parent dir contents:", os.listdir(os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))))

from flask import Flask, render_template, request, redirect, url_for, session, flash
import json
from redis_utils import init_redis_catalog
from dotenv import load_dotenv
from datetime import datetime

from pathlib import Path

# Configuration paths
SECURE_DIR = Path.home() / "code" / "securefiles"
CONFIG_FILE = SECURE_DIR / "redis_config.json"

# Ensure secure directory exists
SECURE_DIR.mkdir(parents=True, exist_ok=True)
# Add this before creating the Flask app
def get_field_type(value):
    if isinstance(value, bool):
        return "boolean"
    elif isinstance(value, int):
        return "integer"
    elif isinstance(value, float):
        return "float"
    elif isinstance(value, str):
        return "string"
    elif isinstance(value, list):
        return "list"
    elif isinstance(value, dict):
        return "dict"
    return type(value).__name__

# Create the app and add the filter
app = Flask(__name__)
app.jinja_env.filters['field_type'] = get_field_type
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

def get_config():
    """Load Redis config from secure file"""
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                return json.load(f)
        return None
    except Exception as e:
        flash(f"Error loading config: {e}", "danger")
        return None

def save_config(config):
    """Save Redis config to secure file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f)
        return True
    except Exception as e:
        flash(f"Error saving config: {e}", "danger")
        return False

def get_catalog():
    """Initialize Redis connection using saved config"""
    config = get_config()
    if not config:
        flash("Redis connection not configured!", "danger")
        return None
    
    try:
        return init_redis_catalog(
            host=config.get('host', "redis.readyforquantum.com"),
            port=config.get('port', 46379),
            password=config.get('password', ""),
            user=config.get('user', "admin"),
            ssl=config.get('ssl', True)
        )
    except Exception as e:
        flash(f"Redis connection failed: {e}", "danger")
        return None

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        config = {
            'host': request.form.get('host', "redis.readyforquantum.com"),
            'port': int(request.form.get('port', 46379)),
            'user': request.form.get('user', "admin"),
            'password': request.form.get('password', ""),
            'ssl': request.form.get('ssl') == 'on'
        }
        
        if save_config(config):
            flash("Redis settings saved securely!", "success")
        return redirect(url_for('index'))
    
    current_config = get_config() or {}
    return render_template('settings.html',
        host=current_config.get('host', ''),
        port=current_config.get('port', ''),
        user=current_config.get('user', ''),
        ssl=current_config.get('ssl', True))

@app.route('/')
def index():
    catalog = get_catalog()
    if not catalog: 
        return redirect(url_for('settings'))

    # Pagination logic
    page = request.args.get('page', 1, type=int)
    per_page = 10

    all_models = list(catalog.load_catalog().items())
    total = len(all_models)
    total_pages = (total + per_page - 1) // per_page

    start = (page - 1) * per_page
    end = start + per_page
    models = all_models[start:end]

    return render_template(
        'index.html',
        models=models,
        page=page,
        total_pages=total_pages
    )

@app.route('/search', methods=['GET', 'POST'])
def search():
    catalog = get_catalog()
    if not catalog:
        return redirect(url_for('settings'))

    # Accept search_term and search_type from both GET and POST
    if request.method == 'POST':
        search_term = request.form.get('search_term', '').strip()
        search_type = request.form.get('search_type', 'i')
        # Redirect to GET with all parameters and page=1
        return redirect(url_for(
            'search',
            search_term=search_term,
            search_type=search_type,
            page=1
        ))
    else:
        search_term = request.args.get('search_term', '').strip()
        search_type = request.args.get('search_type', 'i')

    selected_field = None
    results = []

    # Get field list from first model
    all_models = catalog.load_catalog() or {}
    fields = []
    if all_models:
        first_model = next(iter(all_models.values()))
        fields = list(first_model.keys())

    # Sorting parameters
    order_by = request.args.get('order_by', None)
    order_dir = request.args.get('order_dir', 'asc')
    if order_dir not in ['asc', 'desc']:
        order_dir = 'asc'

    # Handle field number selection
    if search_type.isdigit():
        field_idx = int(search_type) - 1
        if 0 <= field_idx < len(fields):
            selected_field = fields[field_idx]
            search_type = 'field'

    # Always run search on GET or POST, and only filter if search_term is not blank
    for model_id, data in all_models.items():
        matched = False
        match_info = []

        # ID search
        if search_type == 'i':
            if not search_term:
                matched = True
            else:
                print(f"ID search: search_term={search_term!r}, model_id={model_id!r}, match={search_term.lower() in str(model_id).lower()}", flush=True)
                if search_term.lower() in str(model_id).lower():
                    matched = True

        # All fields search
        elif search_type == 'a':
            if not search_term:
                matched = True
            else:
                st = search_term.lower()
                # Check model_id as well as all fields!
                if st in str(model_id).lower():
                    matched = True
                    match_info.append("id")
                # Check ALL fields, not just the first match
                for field, value in data.items():
                    if _value_matches_search(value, st):
                        matched = True
                        match_info.append(field)

        # Specific field search
        elif search_type == 'field' and selected_field:
            value = data.get(selected_field)
            if _value_matches_search(value, search_term):
                matched = True
                match_info.append(selected_field)

        if matched:
            results.append((model_id, data, match_info))

    # Always define pagination variables, even if no results or GET request
    page = request.args.get('page', 1, type=int)
    per_page = 10
    total = len(results)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    # Robust sorting logic: always sort as tuple (type, value) to avoid TypeError
    def get_sort_key(item):
        model_id, data, _ = item
        if order_by == 'id':
            # Always return a tuple of the same types: (priority, string, string)
            return (0, str(model_id).lower(), "")
        elif order_by in data:
            value = data[order_by]
            from dateutil.parser import parse as date_parse
            import datetime

            # Treat blank, None, or missing as "bad" and sort them last
            if value is None or (isinstance(value, str) and value.strip() == ""):
                return (5, "", "")

            # Try date
            if isinstance(value, str):
                try:
                    dt = date_parse(value)
                    return (1, dt.isoformat(), str(value))
                except Exception:
                    pass
            # Try float
            try:
                return (2, float(value), str(value))
            except Exception:
                pass
            # Try int
            try:
                return (2, int(value), str(value))
            except Exception:
                pass
            # Fallback to string, always use a string (never None)
            return (3, str(value).lower(), str(value))
        else:
            return (6, "", "")

    if order_by:
        results.sort(key=get_sort_key, reverse=(order_dir == 'desc'))

    start = (page - 1) * per_page
    end = start + per_page
    paginated_results = results[start:end]

    return render_template('search.html',
        results=paginated_results,
        fields=fields,
        search_term=search_term,
        search_type=search_type,
        page=page,
        total_pages=total_pages,
        order_by=order_by,
        order_dir=order_dir
    )

import re

def _value_matches_search(value, search_term):
    """Check if a field value matches the search term using regex (case-insensitive) and print debug info."""
    if not search_term:
        print(f"_value_matches_search: empty search_term, always True", flush=True)
        return True

    pattern = re.compile(re.escape(search_term), re.IGNORECASE)
    print(f"_value_matches_search: search_term={search_term!r}, value={value!r}, type={type(value)}", flush=True)

    if isinstance(value, bool):
        target = 'true' if value else 'false'
        result = bool(pattern.search(target))
        print(f"  [bool] pattern={pattern.pattern!r}, target={target!r}, result={result}", flush=True)
        return result
    elif isinstance(value, (list, dict)):
        try:
            target = json.dumps(value)
            result = bool(pattern.search(target))
            print(f"  [list/dict] pattern={pattern.pattern!r}, target={target!r}, result={result}", flush=True)
            return result
        except Exception as e:
            target = str(value)
            result = bool(pattern.search(target))
            print(f"  [list/dict fallback] pattern={pattern.pattern!r}, target={target!r}, result={result}, error={e}", flush=True)
            return result
    target = str(value)
    result = bool(pattern.search(target))
    print(f"  [str] pattern={pattern.pattern!r}, target={target!r}, result={result}", flush=True)
    return result


def _convert_to_search_string(value):
    """Convert any field value to searchable string"""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    elif isinstance(value, (list, dict)):
        return json.dumps(value).lower()
    elif value is None:
        return ''
    return str(value).lower()

@app.route('/edit/<path:model_id>', methods=['GET', 'POST'])  # Note the 'path:' prefix
def edit_model(model_id):
    catalog = get_catalog()
    if not catalog: 
        return redirect(url_for('settings'))
    
    # Now model_id will preserve the full path including slashes
    model_data = catalog.get_model(model_id)
    if not model_data:
        flash(f"Model '{model_id}' not found!", "danger")
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        for field in model_data.keys():
            new_value = request.form.get(field)
            if new_value is not None:
                catalog.update_model_field(model_id, field, new_value)
        flash("Model updated successfully!", "success")
        return redirect(url_for('edit_model', model_id=model_id))
    
    return render_template('edit_model.html', model_id=model_id, model=model_data)

@app.route('/add', methods=['GET', 'POST'])
def add_model():
    catalog = get_catalog()
    if not catalog:
        return redirect(url_for('settings'))

    if request.method == 'POST':
        model_id = request.form.get('model_id', '').strip()
        if not model_id:
            flash("Model ID is required!", "danger")
            return render_template('add_model.html')

        # Provide all default fields expected by the app and catalog
        model_data = {
            'converted': False,
            'added': datetime.now().isoformat(),
            'parameters': 0,
            'has_config': False,
            'attempts': 0,
            'error_log': [],
            'quantizations': [],
            "is_moe": False
        }
        # Add/override with any fields from the form (except model_id)
        for key in request.form:
            if key != 'model_id':
                model_data[key] = request.form[key]

        if catalog.get_model(model_id):
            flash("Model ID already exists!", "danger")
            return render_template('add_model.html')

        catalog.add_model(model_id, model_data)
        flash("Model added successfully!", "success")
        return redirect(url_for('edit_model', model_id=model_id))

    return render_template('add_model.html')

@app.route('/import', methods=['GET', 'POST'])
def import_models():
    catalog = get_catalog()
    if not catalog: 
        return redirect(url_for('settings'))
    
    if request.method == 'POST' and 'file' in request.files:
        file = request.files['file']
        if file.filename.endswith('.json'):
            try:
                data = json.load(file)
                models = data.get('models', [])
                result = catalog.import_models_from_list(models)
                flash(f"Imported {result['added']} new models, updated {result['updated']}", "success")
            except Exception as e:
                flash(f"Error processing file: {e}", "danger")
        else:
            flash("Invalid file format! Please upload a JSON file.", "danger")
    
    return render_template('import.html')

@app.route('/backup', methods=['POST'])
def backup():
    catalog = get_catalog()
    if not catalog: 
        return redirect(url_for('settings'))
    
    file_path = f"backup_{datetime.now().isoformat()}.json"
    if catalog.backup_to_file(file_path):
        flash(f"Backup saved to {file_path}", "success")
    else:
        flash("Backup failed!", "danger")
    return redirect(url_for('index'))

@app.route('/delete/<path:model_id>', methods=['POST'])
def delete_model(model_id):
    catalog = get_catalog()
    if not catalog: 
        return redirect(url_for('settings'))

    print(f"Attempting to delete model: {model_id}")
    before = catalog.get_model(model_id)
    print(f"Model before delete: {before}")

    result = catalog.delete_model(model_id)
    print(f"Delete result: {result}")

    after = catalog.get_model(model_id)
    print(f"Model after delete: {after}")

    if result:
        flash("Model deleted successfully!", "success")
    else:
        flash("Delete failed!", "danger")
    return redirect(url_for('index'))

@app.route('/export', methods=['GET'])
def export():
    catalog = get_catalog()
    if not catalog:
        return redirect(url_for('settings'))

    file_path = f"export_{datetime.now().isoformat()}.json"
    if catalog.backup_to_file(file_path):
        from flask import send_file
        return send_file(file_path, as_attachment=True)
    else:
        flash("Export failed!", "danger")
        return redirect(url_for('index'))

@app.route('/converting', methods=['GET', 'POST'])
def converting():
    catalog = get_catalog()
    if not catalog:
        return redirect(url_for('settings'))

    converting_models = catalog.get_converting_models()
    # Ensure all model IDs are strings (in case Redis returns bytes)
    converting_models = [mid.decode() if isinstance(mid, bytes) else mid for mid in converting_models]
    quant_progress_dict = catalog.r.hgetall(catalog.converting_progress_key)
    # Also ensure quant_progress_dict keys/values are strings
    quant_progress_dict = {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in quant_progress_dict.items()
    }
    resumable_models = []
    for model_id, quant in quant_progress_dict.items():
        if model_id not in converting_models:
            model = catalog.get_model(model_id)
            resumable_models.append((model_id, model, quant))

    # Handle removal of stuck models
    if request.method == 'POST':
        model_id = request.form.get('model_id')
        action = request.form.get('action')
        if model_id and hasattr(catalog, "unmark_converting"):
            catalog.unmark_converting(model_id)
            flash(f"Removed '{model_id}' from converting/resumable list.", "success")
            return redirect(url_for('converting'))

    # Show model details for each converting model, including quant progress
    model_details = []
    for model_id in converting_models:
        model = catalog.get_model(model_id)
        quant = catalog.get_quant_progress(model_id)
        model_details.append((model_id, model, quant))

    return render_template(
        'converting.html',
        converting_models=model_details,
        resumable_models=resumable_models
    )

@app.route('/restore', methods=['GET', 'POST'])
def restore():
    catalog = get_catalog()
    if not catalog:
        return redirect(url_for('settings'))

    if request.method == 'POST' and 'file' in request.files:
        file = request.files['file']
        if file.filename.endswith('.json'):
            try:
                # Save uploaded file temporarily
                file_path = f"/tmp/restore_{datetime.now().isoformat()}.json"
                file.save(file_path)
                if catalog.initialize_from_file(file_path):
                    flash("Catalog restored successfully!", "success")
                else:
                    flash("Restore failed!", "danger")
            except Exception as e:
                flash(f"Error processing file: {e}", "danger")
        else:
            flash("Invalid file format! Please upload a JSON file.", "danger")
        return redirect(url_for('index'))

    return render_template('restore.html')

if __name__ == '__main__':
    app.run(debug=True)
