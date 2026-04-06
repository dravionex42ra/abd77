from flask import Flask, render_template, request, jsonify, redirect
import os
import glob
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Config
UPLOAD_FOLDER = 'input'
OUTPUT_FOLDER = 'out'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file and file.filename.endswith('.txt'):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return jsonify({"success": True, "filename": filename})
    return jsonify({"error": "Invalid file type. Please upload a .txt file."}), 400

@app.route('/api/stats')
def get_stats():
    # Sync paths to the output folder
    batches = [os.path.basename(d) for d in glob.glob(os.path.join(OUTPUT_FOLDER, '*')) if os.path.isdir(d)]
    total_files = 0
    batch_details = []
    
    for batch in batches:
        path = os.path.join(OUTPUT_FOLDER, batch)
        # We count all .mp4 files
        count = len([f for f in os.listdir(path) if f.endswith('.mp4')])
        total_files += count
        batch_details.append({"name": batch, "count": count})
    
    return jsonify({
        "total_batches": len(batches),
        "total_downloads": total_files,
        "batches": batch_details
    })

if __name__ == '__main__':
    print("🌐 Sora Unified GUI Archiver Dashboard starting on http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
