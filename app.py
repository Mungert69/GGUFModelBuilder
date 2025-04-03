from flask import Flask, render_template, request, redirect, url_for, session, flash
import json
from redis_utils import init_redis_catalog
import os
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
            host=config.get('host', "redis.freenetworkmonitor.click"),
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
            'host': request.form.get('host', "redis.freenetworkmonitor.click"),
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
    
    models = list(catalog.load_catalog().items())[-10:]
    return render_template('index.html', models=models)

@app.route('/search', methods=['GET', 'POST'])
def search():
    catalog = get_catalog()
    if not catalog:
        return redirect(url_for('settings'))

    search_term = ''
    search_type = 'i'  # Default to ID search
    selected_field = None
    results = []
    
    # Get field list from first model
    all_models = catalog.load_catalog() or {}
    fields = []
    if all_models:
        first_model = next(iter(all_models.values()))
        fields = list(first_model.keys())

    if request.method == 'POST':
        search_type = request.form.get('search_type', 'i')
        search_term = request.form.get('search_term', '').strip().lower()

        # Handle field number selection
        if search_type.isdigit():
            field_idx = int(search_type) - 1
            if 0 <= field_idx < len(fields):
                selected_field = fields[field_idx]
                search_type = 'field'

        for model_id, data in all_models.items():
            matched = False
            match_info = []

            # ID search
            if search_type == 'i':
                if not search_term or search_term in model_id.lower():
                    matched = True
            
            # All fields search
            elif search_type == 'a':
                for field, value in data.items():
                    if _value_matches_search(value, search_term):
                        matched = True
                        match_info.append(field)
                        break
            
            # Specific field search
            elif search_type == 'field' and selected_field:
                value = data.get(selected_field)
                if _value_matches_search(value, search_term):
                    matched = True
                    match_info.append(selected_field)

            if matched:
                results.append((model_id, data, match_info))

    return render_template('search.html',
                         results=results,
                         fields=fields,
                         search_term=search_term,
                         search_type=search_type)

def _value_matches_search(value, search_term):
    """Check if a field value matches the search term"""
    if not search_term:
        return True
    
    if isinstance(value, bool):
        return search_term in ['true', 'yes', '1'] if value else search_term in ['false', 'no', '0']
    elif isinstance(value, (list, dict)):
        try:
            return search_term in json.dumps(value).lower()
        except:
            return search_term in str(value).lower()
    return search_term in str(value).lower()

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

@app.route('/delete/<model_id>', methods=['POST'])
def delete_model(model_id):
    catalog = get_catalog()
    if not catalog: 
        return redirect(url_for('settings'))
    
    if catalog.r.hdel(catalog.catalog_key, model_id):
        flash("Model deleted successfully!", "success")
    else:
        flash("Delete failed!", "danger")
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
