import os
import uuid
from flask import Flask, request, render_template_string
from werkzeug.utils import secure_filename
from openai import OpenAI
import boto3

# ---------- configuration ----------
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
BUCKET_NAME = os.getenv("UPLOAD_BUCKET")          # must be set on the instance
S3_REGION   = os.getenv("AWS_REGION", "us-west-2")

client = OpenAI()                                 # picks up OPENAI_API_KEY
s3     = boto3.client("s3", region_name=S3_REGION)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024   # 8 MB upload limit

INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Ask ChatGPT + Image</title>
  <style>
    body {font-family: sans-serif; margin: 2rem;}
    input[type=text], input[type=file] {width: 60%; padding: .5rem; font-size: 1rem;}
    button {padding: .5rem 1rem; font-size: 1rem; margin-left: .5rem;}
    pre {background: #f6f8fa; padding: 1rem; border-radius: 4px; white-space: pre-wrap;}
  </style>
</head>
<body>
  <h1>Ask ChatGPT (optional image)</h1>
  <form action="/ask" method="post" enctype="multipart/form-data">
    <p><input type="text" name="prompt" placeholder="Enter your question" required /></p>
    <p><input type="file" name="image" accept="image/*" /></p>
    <button type="submit">Ask</button>
  </form>
  {% if answer %}
    <h2>Answer:</h2>
    <pre>{{ answer }}</pre>
  {% endif %}
</body>
</html>
"""

# ---------- helpers ----------
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_s3(file_storage):
    """Upload a Flask FileStorage to S3 and return a 7-day pre-signed GET URL."""
    filename = secure_filename(file_storage.filename)
    ext      = filename.rsplit(".", 1)[1].lower()
    key      = f"uploads/{uuid.uuid4()}.{ext}"
    s3.upload_fileobj(
        file_storage,
        BUCKET_NAME,
        key,
        ExtraArgs={"ContentType": file_storage.mimetype},
    )
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET_NAME, "Key": key},
        ExpiresIn=7 * 24 * 3600,   # 7 days
    )

# ---------- routes ----------
@app.route("/", methods=["GET"])
def index():
    return render_template_string(INDEX_HTML)

@app.route("/ask", methods=["POST"])
def ask():
    prompt = request.form.get("prompt", "").strip()
    if not prompt:
        return render_template_string(INDEX_HTML, answer="Please enter a prompt.")

    # Build the content list (text part always present)
    content_parts = [{"type": "text", "text": prompt}]

    image_file = request.files.get("image")
    if image_file and image_file.filename and allowed_file(image_file.filename):
        try:
            image_url = upload_to_s3(image_file)
            content_parts.append({
                "type": "image_url",
                "image_url": {"url": image_url}
            })
        except Exception as err:
            return render_template_string(INDEX_HTML, answer=f"Image upload error: {err}")

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",          # vision-capable model
            messages=[{"role": "user", "content": content_parts}],
            temperature=0.7,
        )
        answer = response.choices[0].message.content.strip()
    except Exception as err:
        answer = f"Error: {err}"

    return render_template_string(INDEX_HTML, answer=answer)

# ---------- entry point ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
