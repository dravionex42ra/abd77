from flask import Flask, render_template, jsonify
import os
import glob

app = Flask(__name__)

# Basic storage config
DOWNLOADS_DIR = "downloads"
INPUT_DIR = "input"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats')
def get_stats():
    """
    Returns statistics about current batches and total downloads.
    """
    batches = [os.path.basename(d) for d in glob.glob(os.path.join(DOWNLOADS_DIR, '*')) if os.path.isdir(d)]
    
    total_files = 0
    batch_details = []
    
    for batch in batches:
        path = os.path.join(DOWNLOADS_DIR, batch)
        count = len([f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))])
        total_files += count
        batch_details.append({
            "name": batch,
            "count": count
        })
    
    return jsonify({
        "total_batches": len(batches),
        "total_downloads": total_files,
        "batches": batch_details
    })

if __name__ == '__main__':
    # Listen on all interfaces so it's accessible on Cloud Mobile
    app.run(host='0.0.0.0', port=5000, debug=False)
