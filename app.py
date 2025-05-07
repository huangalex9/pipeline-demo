# app.py  ────────────────────────────────────────────────────────────────────
import os, uuid, tempfile, shutil, subprocess, math
from flask import Flask, request, render_template_string
from werkzeug.utils import secure_filename
from openai import OpenAI
import boto3, botocore.exceptions

# ─── Configuration ─────────────────────────────────────────────────────────
ALLOWED_IMG = {"png", "jpg", "jpeg", "gif"}
ALLOWED_VID = {"mp4", "mov", "webm", "mkv", "avi"}
BUCKET      = os.getenv("UPLOAD_BUCKET")
REGION      = os.getenv("AWS_REGION", "us-west-2")
FRAMES      = 4                       # how many thumbnails to pull from a video

client = OpenAI()                     # <- needs OPENAI_API_KEY in env
s3     = boto3.client("s3", region_name=REGION)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024      # 200 MB upload cap

# ─── Simple HTML UI ────────────────────────────────────────────────────────
INDEX_HTML = """
<!doctype html><html lang="en"><head><meta charset="UTF-8" />
<title>ChatGPT + Image/Video</title>
<style>
  body{font-family:sans-serif;margin:2rem}
  input[type=text],input[type=file]{width:60%;padding:.5rem;font-size:1rem}
  button{padding:.5rem 1rem;font-size:1rem;margin-left:.5rem}
  pre{background:#f6f8fa;padding:1rem;border-radius:4px;white-space:pre-wrap}
</style></head><body>
<h1>Ask ChatGPT – optional image <em>or</em> video</h1>
<form action="/ask" method="post" enctype="multipart/form-data">
  <p><input type="text"  name="prompt" placeholder="Enter your question" required></p>
  <p><input type="file" name="media"  accept="image/*,video/*"></p>
  <button type="submit">Ask</button>
</form>
{% if answer %}<h2>Answer:</h2><pre>{{ answer }}</pre>{% endif %}
</body></html>
"""

# ─── Helpers ───────────────────────────────────────────────────────────────
def allowed(filename, exts):         # little util for img / vid checks
    return "." in filename and filename.rsplit(".", 1)[1].lower() in exts

def s3_presign_upload(fileobj, key, mime):
    """Upload stream to S3, return a 7-day presigned GET URL."""
    s3.upload_fileobj(fileobj, BUCKET, key, ExtraArgs={"ContentType": mime})
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": key},
        ExpiresIn=7 * 24 * 3600,
    )

def upload_image(file_storage):
    ext   = secure_filename(file_storage.filename).rsplit(".", 1)[1].lower()
    key   = f"uploads/{uuid.uuid4()}.{ext}"
    return s3_presign_upload(file_storage, key, file_storage.mimetype)

def extract_and_upload_frames(video_storage):
    """Extract `FRAMES` JPEG thumbnails → upload each → return list of URLs."""
    ext = secure_filename(video_storage.filename).rsplit(".", 1)[1].lower()
    tmp_dir  = tempfile.mkdtemp()
    tmp_video = os.path.join(tmp_dir, f"video.{ext}")
    video_storage.save(tmp_video)

    # Use ffprobe to get duration so we can sample evenly
    try:
        import json, shlex
        cmd = ["ffprobe","-v","error","-select_streams","v:0","-show_entries",
               "format=duration","-of","json",tmp_video]
        duration = float(json.loads(subprocess.check_output(cmd))["format"]["duration"])
    except Exception:
        duration = 0  # fall back to ffmpeg’s default frame grab

    # Grab N frames spaced across the video:
    fps_filter = f"fps={FRAMES/duration}" if duration > 0 else "fps=1"
    out_pattern = os.path.join(tmp_dir, "frame_%02d.jpg")
    subprocess.run(
        ["ffmpeg","-i",tmp_video,"-vf",f"{fps_filter},scale=640:-1",
         "-vframes",str(FRAMES),"-q:v","2",out_pattern],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    urls = []
    for jpg in sorted(p for p in os.listdir(tmp_dir) if p.endswith(".jpg")):
        path = os.path.join(tmp_dir, jpg)
        with open(path, "rb") as fh:
            key  = f"uploads/{uuid.uuid4()}.jpg"
            urls.append(s3_presign_upload(fh, key, "image/jpeg"))
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return urls

# ─── Routes ────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    return render_template_string(INDEX_HTML)

@app.route("/ask", methods=["POST"])
def ask():
    prompt = request.form.get("prompt", "").strip()
    if not prompt:
        return render_template_string(INDEX_HTML, answer="Please enter a prompt.")

    content_parts = [{"type": "text", "text": prompt}]

    upload = request.files.get("media")
    if upload and upload.filename:
        fname = upload.filename
        try:
            if allowed(fname, ALLOWED_IMG):
                url = upload_image(upload)
                content_parts.append({"type": "image_url", "image_url": {"url": url}})
            elif allowed(fname, ALLOWED_VID):
                urls = extract_and_upload_frames(upload)
                for url in urls:
                    content_parts.append({"type": "image_url", "image_url": {"url": url}})
            else:
                return render_template_string(INDEX_HTML, answer="Unsupported file type.")
        except (botocore.exceptions.ClientError, subprocess.CalledProcessError, Exception) as err:
            return render_template_string(INDEX_HTML, answer=f"Upload/processing error: {err}")

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": content_parts}],
            temperature=0.7,
        )
        answer = resp.choices[0].message.content.strip()
    except Exception as err:
        answer = f"Error: {err}"

    return render_template_string(INDEX_HTML, answer=answer)

# ─── Local dev entry point ─────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
