import os
import uuid
import logging
import json
import threading
from datetime import datetime, timezone
from flask import Flask, request, jsonify, Response
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from flask import send_from_directory
from flask_cors import CORS

from depth import load_model, generate_depth_map
from tripo import generate_3d_model

# ── Load environment variables ────────────────────────────────────────────────
load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────
UPLOAD_FOLDER  = os.path.join(os.path.dirname(__file__), "uploads")
OUTPUT_FOLDER  = os.path.join(os.path.dirname(__file__), "outputs")
GENERATED_INDEX_PATH = os.path.join(OUTPUT_FOLDER, "generated_index.json")
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "bmp", "webp"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ── App init ──────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)  # Allow cross-origin requests from the frontend
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB hard limit

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ── Load AI model once at startup (not per request) ───────────────────────────
log.info("Loading MiDaS model …")
model, transform, device = load_model()
log.info(f"Model ready on device: {device}")

# ── Progress Tracking ─────────────────────────────────────────────────────────
GENERATION_PROGRESS = {}  # task_id -> {"progress": 0-100, "status": "...", "error": "..."}
GENERATION_PROGRESS_LOCK = threading.Lock()


def update_progress(task_id: str, progress: int, status: str, error: str = None):
    """Update generation progress for a task."""
    with GENERATION_PROGRESS_LOCK:
        GENERATION_PROGRESS[task_id] = {
            "progress": max(0, min(100, progress)),
            "status": status,
            "error": error
        }


def get_progress(task_id: str) -> dict:
    """Get generation progress for a task."""
    with GENERATION_PROGRESS_LOCK:
        return GENERATION_PROGRESS.get(task_id, {"progress": 0, "status": "unknown", "error": None})


# ── Helpers ───────────────────────────────────────────────────────────────────
def _allowed(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _unique_filename(original: str) -> str:
    safe = secure_filename(original)
    return f"{uuid.uuid4().hex}_{safe}"


def _load_generated_index():
    try:
        if not os.path.exists(GENERATED_INDEX_PATH):
            return []
        with open(GENERATED_INDEX_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _append_generated_entry(entry: dict) -> None:
    items = _load_generated_index()
    items.insert(0, entry)
    items = items[:200]
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    with open(GENERATED_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "device": str(device)}), 200


@app.route("/")
def index():
    """Serve the main upload page."""
    with open(os.path.join(os.path.dirname(__file__), "index.html"), "r", encoding="utf-8") as f:
        response = Response(f.read(), mimetype='text/html')
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response


@app.route("/processing.html")
def serve_processing():
    """Serve the processing page."""
    with open(os.path.join(os.path.dirname(__file__), "processing.html"), "r", encoding="utf-8") as f:
        response = Response(f.read(), mimetype='text/html')
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response


@app.route("/viewer.html")
def serve_viewer():
    """Serve the 3D model viewer HTML from front-end folder."""
    with open(os.path.join(os.path.dirname(__file__), "..", "Frontend", "viewer.html"), "r", encoding="utf-8") as f:
        response = Response(f.read(), mimetype='text/html')
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response


@app.route("/viewer-fixed.html")
def serve_viewer_fixed():
    """Serve the fixed 3D model viewer HTML."""
    with open(os.path.join(os.path.dirname(__file__), "viewer-fixed.html"), "r", encoding="utf-8") as f:
        response = Response(f.read(), mimetype='text/html')
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response


@app.route("/list_outputs", methods=["GET"])
def list_outputs():
    """
    GET /list_outputs
    Returns list of generated GLB files with metadata.
    """
    try:
        index = _load_generated_index()

        # Also scan disk for any GLB files not in index
        disk_files = set()
        for name in os.listdir(OUTPUT_FOLDER):
            if name.lower().endswith(".glb"):
                disk_files.add(name)

        indexed_files = {entry["filename"] for entry in index if "filename" in entry}

        # Add any unindexed files to the list
        extra = []
        for name in disk_files - indexed_files:
            mtime = os.path.getmtime(os.path.join(OUTPUT_FOLDER, name))
            extra.append({
                "filename": name,
                "model": f"outputs/{name}",
                "source_image": None,
                "created_at": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
            })

        all_entries = index + extra
        all_entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)

        return jsonify({"models": all_entries}), 200
    except Exception as exc:
        log.exception("Error listing outputs")
        return jsonify({"error": str(exc)}), 500


@app.route("/upload", methods=["POST"])
def upload():
    """
    POST /upload
    Form-data key : "image"
    Returns       : { "depth_map": "outputs/<filename>.jpg" }
    """
    if "image" not in request.files:
        return jsonify({"error": "No file part. Send the image under the key 'image'."}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400
    if not _allowed(file.filename):
        return jsonify({"error": f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}), 415

    input_filename = _unique_filename(file.filename)
    input_path = os.path.join(UPLOAD_FOLDER, input_filename)
    file.save(input_path)
    log.info(f"Saved upload → {input_path}")

    base_name = os.path.splitext(input_filename)[0]
    output_filename = f"{base_name}_depth.jpg"
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)

    try:
        generate_depth_map(input_path, output_path, model, transform, device)
        log.info(f"Depth map saved → {output_path}")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 422
    except Exception:
        log.exception("Unexpected error during depth-map generation")
        return jsonify({"error": "Internal server error during depth-map generation."}), 500

    return jsonify({"depth_map": f"outputs/{output_filename}"}), 200


@app.route("/generate_3d", methods=["POST"])
def generate_3d():
    """
    POST /generate_3d
    Form-data key : "image"
    Returns       : { "task_id": "...", "model": "outputs/<filename>.glb" } (when complete)
    """
    log.info("="*60)
    log.info("🎬 NEW 3D GENERATION REQUEST RECEIVED")
    log.info("="*60)
    
    if "image" not in request.files:
        log.error("❌ No image file provided")
        return jsonify({"error": "No file part. Send the image under the key 'image'."}), 400

    file = request.files["image"]
    if file.filename == "":
        log.error("❌ Empty filename")
        return jsonify({"error": "No file selected."}), 400
    if not _allowed(file.filename):
        log.error(f"❌ File type not allowed: {file.filename}")
        return jsonify({"error": f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}), 415

    input_filename = _unique_filename(file.filename)
    input_path = os.path.join(UPLOAD_FOLDER, input_filename)
    file.save(input_path)
    log.info(f"✓ Image saved: {input_path}")

    base_name = os.path.splitext(input_filename)[0]
    output_filename = f"{base_name}_model.glb"
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)
    
    task_id = str(uuid.uuid4())
    log.info(f"📁 Task ID: {task_id}")
    log.info(f"📁 Output will be saved to: {output_path}")
    log.info("🚀 Starting Tripo AI generation pipeline...")

    # Update progress callback
    def progress_callback(status, progress):
        update_progress(task_id, progress, status)
        log.info(f"📊 Progress: {progress}% - {status}")

    # Run generation in background thread
    def run_generation():
        try:
            success, err = generate_3d_model(input_path, output_path, progress_callback=progress_callback)
            if success:
                log.info(f"✅ 3D model successfully generated!")
                log.info(f"📦 Model location: outputs/{output_filename}")
                _append_generated_entry({
                    "filename": output_filename,
                    "model": f"outputs/{output_filename}",
                    "source_image": input_filename,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "task_id": task_id,
                })
                update_progress(task_id, 100, "success")
                log.info("="*60)
            else:
                log.error(f"❌ 3D model generation failed: {err}")
                update_progress(task_id, 0, "failed", err)
                log.info("="*60)
        except Exception as e:
            log.exception("❌ Unexpected error during 3D model generation")
            log.error(f"Exception details: {str(e)}")
            update_progress(task_id, 0, "failed", str(e))
            log.info("="*60)

    thread = threading.Thread(target=run_generation, daemon=True)
    thread.start()

    # Return task ID immediately with status endpoint
    return jsonify({
        "task_id": task_id,
        "message": "Generation started. Poll /progress/<task_id> for updates."
    }), 202


@app.route("/progress/<task_id>", methods=["GET"])
def check_progress(task_id):
    """
    GET /progress/<task_id>
    Returns: { "progress": 0-100, "status": "...", "model": "..." (if complete) }
    """
    progress_data = get_progress(task_id)
    
    # If complete, fetch the model filename from the index
    if progress_data.get("status") == "success":
        try:
            index = _load_generated_index()
            for entry in index:
                if entry.get("task_id") == task_id:
                    progress_data["model"] = entry.get("model")
                    break
        except Exception:
            pass
    
    return jsonify(progress_data), 200


@app.route("/outputs/<filename>", methods=["GET", "OPTIONS"])
def serve_output(filename):
    # Handle CORS preflight requests
    if request.method == "OPTIONS":
        response = app.make_default_options_response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response
    
    # Sanitize filename to prevent directory traversal
    filename = os.path.basename(filename)
    
    # Get absolute path to the output file
    filepath = os.path.abspath(os.path.join(OUTPUT_FOLDER, filename))
    
    # Log the request
    log.info(f"Serving output: {filename}")
    log.info(f"Full path: {filepath}")
    log.info(f"OUTPUT_FOLDER: {OUTPUT_FOLDER}")
    
    # Verify the file exists
    if not os.path.exists(filepath):
        log.error(f"File not found: {filepath}")
        log.info(f"Files in outputs folder: {os.listdir(OUTPUT_FOLDER) if os.path.exists(OUTPUT_FOLDER) else 'outputs folder does not exist'}")
        return jsonify({"error": f"File not found: {filename}"}), 404
    
    file_size = os.path.getsize(filepath)
    log.info(f"File size: {file_size} bytes")
    
    # Serve the file with proper content type
    try:
        with open(filepath, 'rb') as f:
            file_data = f.read()
        
        response = Response(file_data, mimetype='model/gltf-binary')
        response.headers['Content-Disposition'] = f'inline; filename="{filename}"'
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        log.info(f"✅ File served successfully: {filename}")
        return response
    except Exception as e:
        log.error(f"Error serving file: {e}")
        return jsonify({"error": f"Error serving file: {str(e)}"}), 500


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
