"""
Tripo AI 3D Model Generation Module.

Handles image-to-3D model conversion using Tripo AI API.
"""

import os
import time
import requests
import logging
from typing import Optional, Tuple, Any, Dict
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
TRIPO_API_KEY = os.getenv("TRIPO_API_KEY")
TRIPO_API_BASE_URL = os.getenv("TRIPO_API_BASE_URL", "https://api.tripo3d.ai")

log.info(f"📡 Tripo AI Base URL: {TRIPO_API_BASE_URL}")
if TRIPO_API_KEY:
    log.info("✓ TRIPO_API_KEY loaded from environment")
else:
    log.error("❌ TRIPO_API_KEY not set in environment. 3D generation will fail!")


# ── Headers for API requests ──────────────────────────────────────────────────
def _get_headers():
    """Get headers for Tripo AI API requests."""
    return {
        "Authorization": f"Bearer {TRIPO_API_KEY}",
    }


# ── File Upload to Tripo AI (v2 OpenAPI) ──────────────────────────────────────
def upload_image(image_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Upload image to Tripo AI and get a file token.
    
    Args:
        image_path: Path to the image file.
    
    Returns:
        (file_token, error_message)
    """
    if not os.path.exists(image_path):
        log.error(f"❌ Image file not found: {image_path}")
        return None, "Image file not found"

    try:
        log.info(f"📤 Uploading image to Tripo AI: {os.path.basename(image_path)}")
        with open(image_path, "rb") as f:
            files = {"file": f}
            response = requests.post(
                f"{TRIPO_API_BASE_URL}/v2/openapi/upload",
                headers=_get_headers(),
                files=files,
                timeout=30,
            )
        
        log.info(f"📥 Upload response status: {response.status_code}")
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict):
            log.error("❌ Upload failed: non-JSON response")
            return None, "Upload failed: non-JSON response"

        # Observed response shape:
        # {"code":0,"data":{"image_token":"..."}}  (image_token works as file_token downstream)
        if data.get("code") == 0:
            d = data.get("data") or {}
            file_token = d.get("file_token") or d.get("image_token")
            if not file_token:
                log.error(f"❌ Upload failed: missing token in response: {data}")
                return None, "Upload failed: missing token"
            log.info(f"✅ Image uploaded successfully! Token: {file_token[:20]}...")
            return file_token, None

        message = data.get("message") or data.get("error") or "Upload failed"
        log.error(f"❌ Upload failed: {message} (Code: {data.get('code')})")
        return None, str(message)
            
    except requests.exceptions.RequestException as e:
        msg = f"Request error during image upload: {e}"
        log.error(msg)
        return None, msg
    except Exception as e:
        msg = f"Unexpected error during image upload: {e}"
        log.error(msg)
        return None, msg


# ── Submit 3D Model Generation Request (v2 OpenAPI) ───────────────────────────
def submit_generation_task(file_token: str, file_type: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Submit a 3D model generation task to Tripo AI.
    
    Args:
        file_token: Token from file upload.
        file_type:  File extension/type (e.g. "jpg", "png").
    
    Returns:
        (task_id, error_message)
    """
    try:
        log.info(f"📋 Submitting generation task for file type: {file_type}")
        payload = {
            "type": "image_to_model",
            "file": {
                "type": file_type,
                "file_token": file_token,
            },
            "enable_pbr": True,
        }
        
        response = requests.post(
            f"{TRIPO_API_BASE_URL}/v2/openapi/task",
            headers=_get_headers(),
            json=payload,
            timeout=30,
        )
        
        log.info(f"📥 Task submission response status: {response.status_code}")
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict):
            log.error("❌ Task submission failed: non-JSON response")
            return None, "Task submission failed: non-JSON response"

        if data.get("code") == 0:
            task_id = (data.get("data") or {}).get("task_id")
            if not task_id:
                log.error(f"❌ Task submission failed: missing task_id in response: {data}")
                return None, "Task submission failed: missing task_id"
            log.info(f"✅ Generation task submitted! Task ID: {task_id}")
            return task_id, None

        message = data.get("message") or data.get("error") or "Task submission failed"
        log.error(f"Task submission failed: {message}")
        return None, str(message)
            
    except requests.exceptions.RequestException as e:
        msg = f"Request error during task submission: {e}"
        log.error(msg)
        return None, msg
    except Exception as e:
        msg = f"Unexpected error during task submission: {e}"
        log.error(msg)
        return None, msg


# ── Poll Task Status ──────────────────────────────────────────────────────────
def poll_task_status(task_id: str, max_wait: int = 300, progress_callback=None) -> Tuple[Optional[dict], Optional[str]]:
    """
    Poll the task status until completion or timeout.
    
    Args:
        task_id:   Task ID from generation submission.
        max_wait:  Maximum wait time in seconds (default: 5 minutes).
        progress_callback: Optional callback function(status, elapsed, max_wait) for progress updates.
    
    Returns:
        (task_data, error_message)
    """
    elapsed = 0
    poll_interval = 2  # Start with 2 seconds
    
    while elapsed < max_wait:
        try:
            response = requests.get(
                f"{TRIPO_API_BASE_URL}/v2/openapi/task/{task_id}",
                headers=_get_headers(),
                timeout=30,
            )
            
            response.raise_for_status()
            data = response.json()

            if not isinstance(data, dict):
                log.error("❌ Task query failed: non-JSON response")
                return None, "Task query failed: non-JSON response"

            if data.get("code") != 0:
                message = data.get("message") or data.get("error") or "Task query failed"
                log.error(f"❌ Task query failed: {message}")
                return None, str(message)
            
            task_data = data.get("data", {})
            status = task_data.get("status")
            
            # Calculate progress as a percentage
            progress = min(90, int((elapsed / max_wait) * 100))
            
            log.info(f"⏱️ Task status: {status.upper()} (elapsed: {elapsed}s / {max_wait}s)")
            
            if progress_callback:
                progress_callback(status, progress, elapsed, max_wait)
            
            if status == "success":
                log.info("✅ Task completed successfully!")
                if progress_callback:
                    progress_callback("success", 100, elapsed, max_wait)
                return task_data, None
            elif status == "failed":
                reason = task_data.get("fail_reason", "Unknown error")
                log.error(f"❌ Task failed: {reason}")
                if progress_callback:
                    progress_callback("failed", 0, elapsed, max_wait)
                return None, str(reason)
            
            # Still pending, wait and retry
            log.info(f"⏳ Task pending... waiting {poll_interval}s before next check")
            time.sleep(poll_interval)
            elapsed += poll_interval
            
            # Gradually increase poll interval up to 10 seconds
            poll_interval = min(poll_interval + 1, 10)
            
        except requests.exceptions.RequestException as e:
            msg = f"❌ Request error during status polling: {e}"
            log.error(msg)
            return None, msg
        except Exception as e:
            msg = f"❌ Unexpected error during status polling: {e}"
            log.error(msg)
            return None, msg
    
    log.error(f"❌ Task polling timed out after {max_wait}s")
    return None, f"Task polling timed out after {max_wait}s"


# ── Download 3D Model ─────────────────────────────────────────────────────────
def download_model(task_data: dict, output_path: str, model_format: str = "glb") -> bool:
    """
    Download the generated 3D model as a file.
    
    Args:
        task_data:     Task data dict from polling.
        output_path:   Path where the model will be saved.
        model_format:  Model format ("glb" or "fbx").
    
    Returns:
        True on success, False on failure.
    """
    try:
        # Get the download URL from task data (shape may vary by API version)
        model_url = None
        if isinstance(task_data.get("model"), dict):
            model_url = task_data.get("model", {}).get(model_format)
        if not model_url and isinstance(task_data.get("output"), dict):
            out = task_data.get("output", {})
            # Observed response shape:
            # output: { pbr_model: "https://...glb", ... }
            if model_format == "glb":
                model_url = out.get("pbr_model") or out.get("glb") or out.get("model")
            if not model_url:
                out_model = out.get("model")
                if isinstance(out_model, dict):
                    model_url = out_model.get(model_format)
        
        if not model_url:
            log.error(f"❌ No {model_format} model URL in task data")
            return False
        
        log.info(f"📥 Downloading {model_format.upper()} model...")
        log.info(f"URL: {model_url[:80]}...")
        
        response = requests.get(model_url, timeout=60)
        response.raise_for_status()
        
        log.info(f"✓ Downloaded {len(response.content)} bytes")
        
        # Create parent directory if it doesn't exist
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Write to file
        with open(output_path, "wb") as f:
            f.write(response.content)
        
        log.info(f"✅ Model saved successfully to: {output_path}")
        return True
        
    except requests.exceptions.RequestException as e:
        log.error(f"❌ Request error during model download: {e}")
        return False
    except Exception as e:
        log.error(f"❌ Unexpected error during model download: {e}")
        return False


# ── Main Generation Pipeline ──────────────────────────────────────────────────
def generate_3d_model(image_path: str, output_path: str, progress_callback=None) -> Tuple[bool, Optional[str]]:
    """
    Complete pipeline: upload image → submit task → poll → download model.
    
    Args:
        image_path:  Path to input image.
        output_path: Path where the .glb model will be saved.
        progress_callback: Optional callback function(status, progress) for updates.
    
    Returns:
        (success, error_message)
    """
    log.info("🎬 " + "="*60)
    log.info(f"Starting 3D model generation pipeline")
    log.info(f"Input: {image_path}")
    log.info(f"Output: {output_path}")
    log.info("="*60)
    
    # Step 1: Upload image
    log.info("\n[1/4] 📤 UPLOADING IMAGE TO TRIPO AI")
    if progress_callback:
        progress_callback("uploading", 5)
    ext = (Path(image_path).suffix or "").lstrip(".").lower() or "jpg"
    file_token, err = upload_image(image_path)
    if not file_token:
        log.error(f"❌ Failed to upload image: {err}")
        if progress_callback:
            progress_callback("failed", 0)
        return False, err or "Failed to upload image"
    
    # Step 2: Submit generation task
    log.info("\n[2/4] 📋 SUBMITTING GENERATION TASK")
    if progress_callback:
        progress_callback("submitting", 10)
    task_id, err = submit_generation_task(file_token, ext)
    if not task_id:
        log.error(f"❌ Failed to submit generation task: {err}")
        if progress_callback:
            progress_callback("failed", 0)
        return False, err or "Failed to submit generation task"
    
    # Step 3: Poll for completion
    log.info("\n[3/4] ⏳ POLLING FOR GENERATION (this may take 1-2 minutes)...")
    if progress_callback:
        progress_callback("generating", 20)
    
    def poll_progress_callback(status, progress, elapsed, max_wait):
        """Callback from poll_task_status to track progress."""
        if progress_callback:
            # Map progress from 20-90 range during polling
            mapped_progress = 20 + int((progress / 100) * 70)
            progress_callback(status, mapped_progress)
    
    task_data, err = poll_task_status(task_id, max_wait=300, progress_callback=poll_progress_callback)
    if not task_data:
        log.error(f"❌ Task polling failed or timed out: {err}")
        if progress_callback:
            progress_callback("failed", 0)
        return False, err or "Task polling failed or timed out"
    
    # Step 4: Download model
    log.info("\n[4/4] ⬇️ DOWNLOADING MODEL")
    if progress_callback:
        progress_callback("downloading", 90)
    success = download_model(task_data, output_path, model_format="glb")
    
    if success:
        log.info("\n" + "="*60)
        log.info("✅ 3D MODEL GENERATION COMPLETE!")
        log.info(f"Model saved to: {output_path}")
        log.info("="*60)
        if progress_callback:
            progress_callback("complete", 100)
        return True, None
    else:
        log.error("Failed to download model")
        if progress_callback:
            progress_callback("failed", 0)
        return False, "Failed to download model"
