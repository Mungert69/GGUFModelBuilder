from flask import Flask, render_template, request, redirect, url_for, session, flash
import json
from redis_utils import init_redis_catalog
import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "super-secret-key")

def get_catalog():
    if 'catalog' not in session:
        flash("Redis connection not configured!", "danger")
        return None
    try:
        return init_redis_catalog(
            host=session['redis_host'],
            port=session['redis_port'],
            password=session['redis_password'],
            user=session['redis_user'],
            ssl=session['redis_ssl']
        )
    except Exception as e:
        flash(f"Redis connection failed: {e}", "danger")
        return None

@app.route('/')
def index():
    catalog = get_catalog()
    if not catalog: return redirect(url_for('settings'))
    
    # Show recent 10 models
    models = list(catalog.load_catalog().items())[-10:]
    return render_template('index.html', models=models)

@app.route('/settings', methods=['GET', 'POST'))
def settings():
    if request.method == 'POST':
        session['redis_host'] = request.form.get('host') or "redis.readyforquantum.com"
        session['redis_port'] = int(request.form.get('port') or 46379)
        session['redis_user'] = request.form.get('user') or "admin"
        session['redis_password'] = request.form.get('password') or os.getenv("REDIS_PASSWORD")
        session['redis_ssl'] = 'ssl' in request.form
        flash("Redis settings updated!", "success")
        return redirect(url_for('index'))
    
    return render_template('settings.html'))

@app.route('/search', methods=['GET', 'POST'))
def search():
    catalog = get_catalog()
    if not catalog: return redirect(url_for('settings'))
    
    if request.method == 'POST':
        search_type = request.form.get('search_type')
        search_term = request.form.get('search_term', '').lower()
        
        all_models = catalog.load_catalog()
        results = []
        
        for model_id, data in all_models.items():
            if search_type == 'id':
                if search_term in model_id.lower():
                    results.append((model_id, data))
            elif search_type == 'all':
                if any(search_term in str(v).lower() for v in data.values()):
                    results.append((model_id, data))
            else:
                field = request.form.get('field')
                value = str(data.get(field, '')).lower()
                if search_term in value:
                    results.append((model_id, data))
        
        return render_template('search.html', 
                            results=results,
                            fields=list(all_models.values())[0].keys() if all_models else [])
    
    return render_template('search.html'))

@app.route('/edit/<model_id>', methods=['GET', 'POST'))
def edit_model(model_id):
    catalog = get_catalog()
    if not catalog: return redirect(url_for('settings'))
    
    model_data = catalog.get_model(model_id)
    if not model_data:
        flash("Model not found!", "danger")
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        # Handle field updates
        for field in model_data.keys():
            new_value = request.form.get(field)
            if new_value is not None:
                # Add type conversion logic here
                catalog.update_model_field(model_id, field, new_value)
        flash("Model updated successfully!", "success")
        return redirect(url_for('edit_model', model_id=model_id))
    
    return render_template('edit_model.html', model_id=model_id, model=model_data))

@app.route('/import', methods=['GET', 'POST'))
def import_models():
    catalog = get_catalog()
    if not catalog: return redirect(url_for('settings'))
    
    if request.method == 'POST' and 'file' in request.files:
        file = request.files['file']
        if file.filename.endswith('.json'):
            data = json.load(file)
            models = data.get('models', [])
            result = catalog.import_models_from_list(models)
            flash(f"Imported {result['added']} new models, updated {result['updated']}", "success"))
        else:
            flash("Invalid file format!", "danger")
    
    return render_template('import.html'))

@app.route('/backup', methods=['POST'))
def backup():
    catalog = get_catalog()
    if not catalog: return redirect(url_for('settings'))
    
    file_path = f"backup_{datetime.now().isoformat()}.json"
    if catalog.backup_to_file(file_path):
        flash(f"Backup saved to {file_path}", "success"))
    else:
        flash("Backup failed!", "danger")
    return redirect(url_for('index'))

@app.route('/delete/<model_id>', methods=['POST'))
def delete_model(model_id):
    catalog = get_catalog()
    if not catalog: return redirect(url_for('settings'))
    
    if catalog.r.hdel(catalog.catalog_key, model_id):
        flash("Model deleted successfully!", "success")
    else:
        flash("Delete failed!", "danger")
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
