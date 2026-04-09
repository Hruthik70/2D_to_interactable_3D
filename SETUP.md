# AI Backend - Setup & Usage Guide

## Installation

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Tripo AI API Key
Create or update the `.env` file in your project root:

```env
TRIPO_API_KEY=your_api_key_from_tripo_ai
TRIPO_API_BASE_URL=https://api.tripo3d.ai
FLASK_ENV=development
DEBUG=False
```

**Get your API Key:**
1. Sign up at [Tripo AI](https://www.tripo3d.ai/)
2. Navigate to your API dashboard
3. Generate an API key
4. Copy it to the `.env` file

### 3. Run the Server
```bash
python app.py
```

The server will start on `http://localhost:5000`

---

## API Endpoints

### 1. Health Check
```bash
GET /health
```
Response:
```json
{
  "status": "ok",
  "device": "cuda" or "cpu"
}
```

### 2. Generate Depth Map (Existing)
```bash
POST /upload
Content-Type: multipart/form-data

Form Data:
- image: <image_file>
```

Response:
```json
{
  "depth_map": "outputs/filename_depth.jpg"
}
```

### 3. Generate 3D Model (New)
```bash
POST /generate_3d
Content-Type: multipart/form-data

Form Data:
- image: <image_file>
```

Response:
```json
{
  "model": "outputs/filename_model.glb",
  "status": "success"
}
```

---

## Usage Examples

### Using cURL

**Generate 3D Model:**
```bash
curl -X POST http://localhost:5000/generate_3d \
  -F "image=@path/to/image.jpg"
```

### Using Python Requests
```python
import requests

with open("image.jpg", "rb") as f:
    files = {"image": f}
    response = requests.post("http://localhost:5000/generate_3d", files=files)
    print(response.json())
```

### Using JavaScript/Fetch
```javascript
const formData = new FormData();
formData.append("image", fileInput.files[0]);

fetch("http://localhost:5000/generate_3d", {
  method: "POST",
  body: formData
})
.then(res => res.json())
.then(data => console.log(data))
.catch(err => console.error(err));
```

---

## Project Structure

```
ai_backend/
├── app.py              # Flask application & routes
├── depth.py            # Depth map generation (MiDaS)
├── tripo.py            # Tripo AI API integration ✓ NEW
├── .env                # Environment variables ✓ NEW
├── requirements.txt    # Python dependencies
├── uploads/            # Uploaded images
└── outputs/            # Generated models & depth maps
```

---

## How It Works

### 3D Model Generation Pipeline

1. **Upload Image** → Sent to Tripo AI API
2. **Submit Task** → Receives task ID
3. **Poll Status** → Wait for model generation (1-2 min)
4. **Download Model** → Save .glb file locally
5. **Return Path** → Send to frontend for 3D viewer

### Processing Time
- Typical: 1-2 minutes
- API handles heavy lifting; local server just orchestrates

---

## Supported Image Formats

- JPG / JPEG
- PNG
- BMP
- WebP

Maximum file size: **16 MB**

---

## Best Practices

### Image Quality
- Simple objects work best (apple, bottle, chair)
- Clear, well-lit images
- Avoid cluttered backgrounds
- Single object focus recommended

### API Limits
- Check your Tripo AI quota
- Each generation credits 1 API call
- Monitor your usage on dashboard

### Error Handling
If you see errors:
1. Check `.env` has correct API key
2. Verify image is valid format
3. Check internet connection
4. Review logs in terminal for details

---

## Testing

### Test Depth Map Generation
```bash
curl -X POST http://localhost:5000/upload \
  -F "image=@test_image.jpg"
```

### Test 3D Model Generation
```bash
curl -X POST http://localhost:5000/generate_3d \
  -F "image=@test_image.jpg"
```

Generated files will be in `outputs/` folder

---

## Troubleshooting

### "TRIPO_API_KEY not set"
- Make sure `.env` file exists
- Verify API key is correct (no extra spaces)
- Restart the server after updating `.env`

### "Image upload failed"
- Check image format is supported
- Ensure image file is not corrupted
- Verify file size < 16MB

### "Task polling timed out"
- Generation may be taking longer
- Check Tripo AI dashboard for task status
- Try with a simpler image

### "Cannot download model"
- API may be down temporarily
- Check network connection
- Verify API key is still valid

---

## Next Steps

1. ✓ Copy your Tripo AI API key to `.env`
2. ✓ Install dependencies: `pip install -r requirements.txt`
3. ✓ Run server: `python app.py`
4. ✓ Test endpoints
5. ✓ Integrate frontend for 3D viewer display

Enjoy! 🚀
