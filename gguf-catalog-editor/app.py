import sys
import os
import re
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

    # Pagination logic using Redis HSCAN for efficiency
    page = request.args.get('page', 1, type=int)
    per_page = 10

    # Use HSCAN to fetch only the models for the current page
    start = (page - 1) * per_page
    end = start + per_page

    # Get all model IDs (fast, as it's just keys)
    all_model_ids = list(catalog.r.hkeys(catalog.catalog_key))
    total = len(all_model_ids)
    total_pages = (total + per_page - 1) // per_page

    # Get only the model IDs for the current page
    page_model_ids = all_model_ids[start:end]
    # Fetch only these models from Redis
    if page_model_ids:
        page_models = catalog.r.hmget(catalog.catalog_key, page_model_ids)
        models = list(zip(page_model_ids, [json.loads(m) if m else {} for m in page_models]))
    else:
        models = []

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

    # Get all model IDs (fast, as it's just keys)
    all_model_ids = list(catalog.r.hkeys(catalog.catalog_key))
    fields = []
    if all_model_ids:
        # Fetch the first model to get field names
        first_model_json = catalog.r.hget(catalog.catalog_key, all_model_ids[0])
        if first_model_json:
            first_model = json.loads(first_model_json)
            fields = list(first_model.keys())

    # Sorting parameters
    order_by = request.args.get('order_by', None)
    order_dir = request.args.get('order_dir', 'asc')
    if order_dir not in ['asc', 'desc']:
        order_dir = 'asc'

    # Handle field number selection
    selected_field = None
    if search_type.isdigit() and fields:
        field_idx = int(search_type) - 1
        if 0 <= field_idx < len(fields):
            selected_field = fields[field_idx]

    # Filter model IDs based on search
    matched_ids = []
    match_infos = {}
    st = search_term.lower()
    for model_id in all_model_ids:
        matched = False
        match_info = []
        # ID search
        if search_type == 'i':
            if not search_term or st in str(model_id).lower():
                matched = True
        # All fields search
        elif search_type == 'a':
            if not search_term:
                matched = True
            else:
                if st in str(model_id).lower():
                    matched = True
                    match_info.append("id")
                # Fetch model JSON only if needed
                model_json = catalog.r.hget(catalog.catalog_key, model_id)
                if model_json:
                    data = json.loads(model_json)
                    for field, value in data.items():
                        if _value_matches_search(value, st):
                            matched = True
                            match_info.append(field)
        # Specific field search
        elif search_type.isdigit() and selected_field:
            # Fetch only the field value
            model_json = catalog.r.hget(catalog.catalog_key, model_id)
            if model_json:
                data = json.loads(model_json)
                value = data.get(selected_field)
                if _value_matches_search(value, search_term):
                    matched = True
                    match_info.append(selected_field)
        if matched:
            matched_ids.append(model_id)
            match_infos[model_id] = match_info

    # Always define pagination variables, even if no results or GET request
    page = request.args.get('page', 1, type=int)
    per_page = 10
    total = len(matched_ids)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    # Pagination
    start = (page - 1) * per_page
    end = start + per_page
    page_model_ids = matched_ids[start:end]

    # Fetch only the models for the current page
    if page_model_ids:
        page_models = catalog.r.hmget(catalog.catalog_key, page_model_ids)
        paginated_results = []
        for model_id, model_json in zip(page_model_ids, page_models):
            if model_json:
                data = json.loads(model_json)
                paginated_results.append((model_id, data, match_infos.get(model_id, [])))
    else:
        paginated_results = []

    # Robust sorting logic: always sort as tuple (type, value) to avoid TypeError
    def get_sort_key(item):
        model_id, data, _ = item
        if order_by == 'id':
            return (0, str(model_id).lower(), "")
        elif order_by in data:
            value = data[order_by]
            from dateutil.parser import parse as date_parse
            import datetime

            if value is None or (isinstance(value, str) and value.strip() == ""):
                return (5, "", "")

            if isinstance(value, str):
                try:
                    dt = date_parse(value)
                    return (1, dt.isoformat(), str(value))
                except Exception:
                    pass
            try:
                return (2, float(value), str(value))
            except Exception:
                pass
            try:
                return (2, int(value), str(value))
            except Exception:
                pass
            return (3, str(value).lower(), str(value))
        else:
            return (6, "", "")

    if order_by:
        paginated_results.sort(key=get_sort_key, reverse=(order_dir == 'desc'))

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
        # Only update fields that have changed, and update in a single Redis call
        updated_model = model_data.copy()
        changed = False
        for field in model_data.keys():
            new_value = request.form.get(field)
            old_value = updated_model.get(field, "")
            # Convert booleans and numbers to string for comparison with form data
            if isinstance(old_value, bool):
                old_value_str = str(old_value).lower()
            elif old_value is None:
                old_value_str = ""
            else:
                old_value_str = str(old_value)
            if new_value is not None and old_value_str != new_value:
                # Try to preserve type: convert to bool/int/float if possible
                if isinstance(old_value, bool):
                    updated_model[field] = new_value.lower() == "true"
                elif isinstance(old_value, int):
                    try:
                        updated_model[field] = int(new_value)
                    except Exception:
                        updated_model[field] = new_value
                elif isinstance(old_value, float):
                    try:
                        updated_model[field] = float(new_value)
                    except Exception:
                        updated_model[field] = new_value
                elif isinstance(old_value, list) or isinstance(old_value, dict):
                    try:
                        updated_model[field] = json.loads(new_value)
                    except Exception:
                        updated_model[field] = new_value
                else:
                    updated_model[field] = new_value
                changed = True
        if changed:
            # Save the updated model in one Redis call
            catalog.r.hset(catalog.catalog_key, model_id, json.dumps(updated_model))
            flash("Model updated successfully!", "success")
        else:
            flash("No changes detected.", "info")
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
            'has_config': True,
            'attempts': 0,
            'error_log': [],
            'quantizations': [],
            "is_moe": False
        }
        # Add/override with any fields from the form (except model_id)
        for key in request.form:
            if key != 'model_id':
                model_data[key] = request.form[key]

        # Use Redis hexists for fast existence check
        if catalog.r.hexists(catalog.catalog_key, model_id):
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

    result = catalog.delete_model(model_id)
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

    # Warn if catalog is very large
    total_models = catalog.r.hlen(catalog.catalog_key)
    if total_models > 1000:
        flash(f"Warning: Catalog is large ({total_models} models). Export may take a while.", "warning")

    file_path = f"export_{datetime.now().isoformat()}.json"
    if catalog.backup_to_file(file_path):
        from flask import send_file
        return send_file(file_path, as_attachment=True)
    else:
        flash("Export failed!", "danger")
        return redirect(url_for('index'))

@app.route('/mark_failed/<path:model_id>', methods=['POST'])
def mark_failed(model_id):
    catalog = get_catalog()
    if not catalog:
        return redirect(url_for('settings'))
    catalog.mark_failed(model_id)
    # Do NOT remove from converting, do NOT clear progress!
    from flask import flash
    flash(f"Marked '{model_id}' as failed/resumable. You can now resume it.", "success")
    return redirect(url_for('converting'))

@app.route('/converting', methods=['GET', 'POST'])
def converting():
    catalog = get_catalog()
    if not catalog:
        return redirect(url_for('settings'))

    converting_models = catalog.get_converting_models()
    converting_models = [mid.decode() if isinstance(mid, bytes) else mid for mid in converting_models]
    quant_progress_dict = catalog.r.hgetall(catalog.converting_progress_key)
    quant_progress_dict = {
        (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
        for k, v in quant_progress_dict.items()
    }
    failed_models = catalog.r.smembers("model:converting:failed")
    failed_models = [mid.decode() if isinstance(mid, bytes) else mid for mid in failed_models]

    # Batch fetch all needed models in one Redis call
    all_needed_ids = list(set(converting_models + failed_models))
    if all_needed_ids:
        all_models_json = catalog.r.hmget(catalog.catalog_key, all_needed_ids)
        all_models = {
            model_id: json.loads(model_json) if model_json else None
            for model_id, model_json in zip(all_needed_ids, all_models_json)
        }
    else:
        all_models = {}

    running_models = []
    failed_table_models = []

    for model_id in converting_models:
        if model_id in failed_models:
            continue
        model = all_models.get(model_id)
        quant = quant_progress_dict.get(model_id)
        running_models.append((model_id, model, quant))

    for model_id in failed_models:
        model = all_models.get(model_id)
        quant = quant_progress_dict.get(model_id)
        failed_table_models.append((model_id, model, quant))

    # Handle removal of stuck models
    if request.method == 'POST':
        model_id = request.form.get('model_id')
        action = request.form.get('action')
        if model_id and hasattr(catalog, "unmark_converting"):
            catalog.unmark_converting(model_id)
            flash(f"Removed '{model_id}' from converting/resumable list.", "success")
            return redirect(url_for('converting'))

    return render_template(
        'converting.html',
        running_models=running_models,
        failed_table_models=failed_table_models
    )

@app.route('/edit_quant_progress/<path:model_id>', methods=['POST'])
def edit_quant_progress(model_id):
    catalog = get_catalog()
    if not catalog:
        return redirect(url_for('settings'))
    quant = request.form.get('quant', '').strip()
    if quant:
        catalog.set_quant_progress(model_id, quant)
        flash(f"Updated quant progress for {model_id} to '{quant}'", "success")
    else:
        # If blank, clear progress
        catalog.set_quant_progress(model_id, "")
        flash(f"Cleared quant progress for {model_id}", "info")
    return redirect(url_for('converting'))

@app.route('/batch_edit_quant_progress', methods=['POST'])
def batch_edit_quant_progress():
    catalog = get_catalog()
    if not catalog:
        return redirect(url_for('settings'))
    selected_models = request.form.getlist('selected_models')
    quant = request.form.get('quant', '').strip()
    if not selected_models:
        flash("No models selected for batch update.", "warning")
        return redirect(url_for('converting'))
    # Batch update quant progress using a Redis pipeline for performance
    with catalog.r.pipeline() as pipe:
        for model_id in selected_models:
            pipe.hset(catalog.converting_progress_key, model_id, quant)
        pipe.execute()
    flash(f"Updated quant progress for {len(selected_models)} models to '{quant}'", "success")
    return redirect(url_for('converting'))

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
                # Check file size before saving
                file.seek(0, os.SEEK_END)
                size_mb = file.tell() / (1024 * 1024)
                file.seek(0)
                if size_mb > 50:
                    flash(f"Warning: Restore file is large ({size_mb:.1f} MB). Restore may take a while.", "warning")
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
