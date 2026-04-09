import cv2
import torch
import numpy as np
from PIL import Image


def load_model():
    """Load MiDaS model, and transforms. Call once at startup."""
    model_type = "MiDaS_small"

    model = torch.hub.load("intel-isl/MiDaS", model_type, skip_validation=True)
    model.eval()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    transforms = torch.hub.load("intel-isl/MiDaS", "transforms", skip_validation=True)
    transform = transforms.small_transform

    return model, transform, device


def generate_depth_map(image_path: str, output_path: str, model, transform, device) -> str:
    """
    Generate a depth map from a 2D image using MiDaS.

    Args:
        image_path:  Path to the uploaded input image.
        output_path: Path where the depth map will be saved.
        model:       Loaded MiDaS model.
        transform:   MiDaS preprocessing transform.
        device:      Torch device (cpu / cuda).

    Returns:
        output_path on success.

    Raises:
        ValueError: If the image cannot be read or has an unsupported format.
    """
    # ── Load & validate image ──────────────────────────────────────────────
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Cannot read image at '{image_path}'. "
                         "Ensure it is a valid JPG, PNG, or BMP file.")

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # ── Preprocess ────────────────────────────────────────────────────────
    input_batch = transform(img_rgb).to(device)

    # ── Inference ─────────────────────────────────────────────────────────
    with torch.no_grad():
        prediction = model(input_batch)

        # Upsample back to original image resolution
        prediction = torch.nn.functional.interpolate(
            prediction.unsqueeze(1),
            size=img_rgb.shape[:2],
            mode="bicubic",
            align_corners=False,
        ).squeeze()

    depth = prediction.cpu().numpy()

    # ── Normalise to 0-255 (uint8 grayscale) ──────────────────────────────
    depth_min, depth_max = depth.min(), depth.max()
    if depth_max - depth_min > 1e-6:
        depth_norm = (depth - depth_min) / (depth_max - depth_min)
    else:
        depth_norm = np.zeros_like(depth)

    depth_uint8 = (depth_norm * 255).astype(np.uint8)

    # ── Save ──────────────────────────────────────────────────────────────
    cv2.imwrite(output_path, depth_uint8)

    return output_path
