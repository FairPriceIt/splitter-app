from flask import Flask, request, jsonify, send_file
import os
import uuid
from werkzeug.utils import secure_filename
import demucs.separate
from pathlib import Path
import torch

app = Flask(__name__)

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
        demucs.separate.main(["--mp3","--two-stems","vocals","-n","mdx_extra",input_path,"-o",output_folder,"--device",'cuda' if torch.cuda.is_available() else 'cpu'])
        # Save results
        base_name = Path(input_path).stem
        output_dir = Path(output_folder) / base_name
        output_dir.mkdir(parents=True, exist_ok=True)

        vocals_path = output_dir / "vocals.wav"
        music_path = output_dir / "no_vocals.wav"
        return str(vocals_path), str(music_path)
    except Exception as e:
        raise RuntimeError(f"Demucs processing failed: {e}")


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected for uploading"}), 400

    if file:
        # Save the uploaded file
        filename = secure_filename(file.filename)
        file_id = str(uuid.uuid4())
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{file_id}_{filename}")
        file.save(input_path)

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
def serve_file(filename):
    full_path = os.path.join(app.config['OUTPUT_FOLDER'], filename)
    if not os.path.exists(full_path):
        return jsonify({"error": "File not found"}), 404
    return send_file(full_path)


if __name__ == '__main__':
    app.run(debug=True)
