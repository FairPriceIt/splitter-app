from flask import Flask, request, jsonify, send_file,send_from_directory
from flask_cors import CORS,cross_origin
import os
import uuid
from werkzeug.utils import secure_filename
import demucs.separate
from pathlib import Path
import torch
from demucs import pretrained
import requests
MODEL_NAME="htdemucs"

model = pretrained.get_model(MODEL_NAME)

app = Flask(__name__)
cors=CORS(app)

app.config['CORS_HEADERS'] = 'Content-Type'

# Configuration
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def split_audio(input_path, output_folder):
    """
    Splits the audio file using the Demucs model.
    """
    try:
        demucs.separate.main(["--mp3","--two-stems","vocals","--mp3-bitrate", "160","-n",MODEL_NAME,input_path,"-o",output_folder,"--device",'cuda' if torch.cuda.is_available() else 'cpu', ])
        # Save results
        base_name = Path(input_path).stem
        output_dir = Path(output_folder)/MODEL_NAME / base_name
        output_dir.mkdir(parents=True, exist_ok=True)

        vocals_path = output_dir / "vocals.mp3"
        music_path = output_dir / "no_vocals.mp3"
        return str(vocals_path), str(music_path)
    except Exception as e:
        raise RuntimeError(f"Demucs processing failed: {e}")

def download_file_from_url(url, upload_folder):
    """Download a file from a URL and save it locally."""
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        filename = str(uuid.uuid4()) + "_downloaded_audio.mp3"
        file_path = os.path.join(upload_folder, filename)
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                f.write(chunk)
        return file_path
    else:
        raise RuntimeError(f"Failed to download file from URL: {response.status_code}")


@app.route('/upload', methods=['POST'])
@cross_origin()
def upload_file():
    if 'file' not in request.files and 'url' not in request.form:
        return jsonify({"error": "No file or URL provided"}), 400

    input_path = None
    
    if 'file' in request.files:
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected for uploading"}), 400

        filename = secure_filename(file.filename)
        file_id = str(uuid.uuid4())
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{file_id}_{filename}")
        file.save(input_path)

    elif 'url' in request.form:
        url = request.form['url']
        try:
            input_path = download_file_from_url(url, app.config['UPLOAD_FOLDER'])
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 400
    try:
        # Process the file with Demucs
        vocals_path, music_path = split_audio(input_path, app.config['OUTPUT_FOLDER'])

        # Construct public paths
        vocals_url = f"/files/{os.path.relpath(vocals_path, app.config['OUTPUT_FOLDER'])}"
        music_url = f"/files/{os.path.relpath(music_path, app.config['OUTPUT_FOLDER'])}"

        return jsonify({"vocals_url": vocals_url, "no_vocals_url": music_url})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500


@app.route('/files/<path:filename>', methods=['GET'])
@cross_origin()
def serve_file(filename):
    full_path = os.path.join(app.config['OUTPUT_FOLDER'], filename)
    print(full_path)
    if not os.path.exists(full_path):
        return jsonify({"error": "File not found"}), 404
    return send_file(full_path)

@app.route('/')
def send_index():
    return send_from_directory('static', 'index.html')

# if __name__ == 'app':
#     addr=5000
#     http_server = WSGIServer(('', addr), app)
#     print("Listening on ",addr)
#     http_server.serve_forever()
