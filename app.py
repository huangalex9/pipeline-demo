# app.py  ────────────────────────────────────────────────────────────────────
from __future__ import annotations
import os, uuid, tempfile, shutil, subprocess, json, time
from pathlib import Path

import cv2
import boto3, botocore.exceptions
import pandas as pd
from werkzeug.utils import secure_filename
from moviepy.editor import VideoFileClip
from flask import Flask, request, render_template_string

from openai import OpenAI
from llm_confidence.logprobs_handler import LogprobsHandler      # external util

# ─── Runtime / env config ──────────────────────────────────────────────────
ALLOWED_IMG   = {"png", "jpg", "jpeg", "gif"}
ALLOWED_VID   = {"mp4", "mov", "webm", "mkv", "avi"}
BUCKET        = os.getenv("UPLOAD_BUCKET")
REGION        = os.getenv("AWS_REGION", "us-west-2")
SKILL_CSV     = os.getenv("SKILL_DEF_PATH", "resources/skill_definitions.csv")
IMAGE_MODEL   = os.getenv("IMAGE_MODEL", "gpt-4o-mini")
AUDIO_MODEL   = os.getenv("AUDIO_MODEL", "whisper-1")
TEXT_MODEL    = os.getenv("TEXT_MODEL", "deepseek-chat")
FRAMES        = 4             # thumbnails per video
MAX_RETRIES   = 3
RETRY_DELAY   = 1.0

client = OpenAI()             # needs OPENAI_API_KEY in env
s3     = boto3.client("s3", region_name=REGION)

# ─── Flask basics ──────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024   # 200 MB uploads

HTML_PAGE = """
<!doctype html><html lang="en"><head><meta charset="UTF-8" />
<title>ChatGPT + Image/Video</title>
<style>body{font-family:sans-serif;margin:2rem}
input[type=text],input[type=file]{width:60%;padding:.5rem;font-size:1rem}
button{padding:.5rem 1rem;font-size:1rem;margin-left:.5rem}
pre{background:#f6f8fa;padding:1rem;border-radius:4px;white-space:pre-wrap}</style>
</head><body>
<h1>Ask ChatGPT – optional image <em>or</em> video</h1>
<form action="/ask" method="post" enctype="multipart/form-data">
  <p><input type="text"  name="prompt" placeholder="Enter your question" required></p>
  <p><input type="file" name="media"  accept="image/*,video/*"></p>
  <button type="submit">Ask</button>
</form>
{% if answer %}<h2>Answer:</h2><pre>{{ answer }}</pre>{% endif %}
</body></html>
"""

# ─── Helper: load & clean skill list ───────────────────────────────────────
def prepare_skill_df(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path).copy()
    df.columns = df.columns.str.strip()
    if "Skill" not in df.columns:
        df.rename(columns={df.columns[0]: "Skill"}, inplace=True)
    return df.reset_index(drop=True)

SKILL_DF = prepare_skill_df(SKILL_CSV)
LOG_HANDLER = LogprobsHandler()

# ─── S3 utilities ─────────────────────────────────────────────────────────
def s3_presign_upload(fileobj, key, mime):
    s3.upload_fileobj(fileobj, BUCKET, key, ExtraArgs={"ContentType": mime})
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": key},
        ExpiresIn=7 * 24 * 3600,
    )

def upload_image(file_storage):
    ext = secure_filename(file_storage.filename).rsplit(".", 1)[1].lower()
    key = f"uploads/{uuid.uuid4()}.{ext}"
    return s3_presign_upload(file_storage, key, file_storage.mimetype)

# ─── Video helpers (thumbnail + audio) ─────────────────────────────────────
def extract_thumbnails(video_fh, frames=FRAMES):
    """Return list of presigned S3 URLs for JPEG thumbnails."""
    tmp_dir   = tempfile.mkdtemp()
    tmp_path  = os.path.join(tmp_dir, "video")
    video_fh.save(tmp_path)

    # duration → sampling FPS
    try:
        meta = json.loads(subprocess.check_output([
            "ffprobe","-v","error","-select_streams","v:0","-show_entries",
            "format=duration","-of","json",tmp_path
        ]))
        dur = float(meta["format"]["duration"])
    except Exception:
        dur = 0
    fps_filter = f"fps={frames/dur}" if dur > 0 else "fps=1"
    subprocess.run(
        ["ffmpeg","-i",tmp_path,"-vf",f"{fps_filter},scale=640:-1",
         "-vframes",str(frames),"-q:v","2",os.path.join(tmp_dir,"f%02d.jpg")],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    urls = []
    for jpg in sorted(Path(tmp_dir).glob("f*.jpg")):
        with open(jpg, "rb") as fh:
            key = f"uploads/{uuid.uuid4()}.jpg"
            urls.append(s3_presign_upload(fh, key, "image/jpeg"))
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return urls

def extract_audio_to_tmp(video_fh) -> Path:
    """Return Path to temp MP3 extracted from uploaded video."""
    tmp_dir  = tempfile.mkdtemp()
    raw_path = os.path.join(tmp_dir, "raw")
    video_fh.save(raw_path)
    mp3_path = os.path.join(tmp_dir, "audio.mp3")
    clip = VideoFileClip(raw_path)
    clip.audio.write_audiofile(mp3_path, logger=None)
    clip.close()
    return Path(mp3_path)

# ─── LLM-based processing steps ───────────────────────────────────────────
def whisper_transcribe(audio_path: Path) -> str:
    with open(audio_path, "rb") as af:
        resp = client.audio.transcriptions.create(
            model=AUDIO_MODEL, file=af, response_format="text"
        )
    return resp

def summarize_frames(prompt, urls: list[str]) -> str:
    parts = [{"type":"text","text":prompt}] + [
        {"type":"image_url","image_url":{"url":u}} for u in urls
    ]
    resp = client.chat.completions.create(
        model=IMAGE_MODEL,
        messages=[{"role":"user","content":parts}],
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()

def label_skills(entry: dict) -> list[str]:
    """Return top-N skill names + confidence dict (printed to server log)."""
    system = (
        "You are an expert skill-tagger for Delta Air Lines training videos.\n"
        "Select the 3-5 best-fitting labels from the list below and reply with "
        "ONE JSON object whose keys are label_1, label_2… and whose values "
        "are integer ids only.\n\n" +
        "; ".join(f"(id:{i}, label:{n})" for i, n in SKILL_DF["Skill"].items()) +
        '\n\nEXAMPLE: {"label_1":4,"label_2":17,"label_3":9}'
    )
    user   = "\n".join(f"{k}: {entry[k]}" for k in ("title","transcript","summary"))
    resp   = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[{"role":"system","content":system},{"role":"user","content":user}],
        logprobs=True, top_logprobs=2, response_format={"type":"json_object"},
        temperature=0
    )
    reply  = json.loads(resp.choices[0].message.content)
    tokens = resp.choices[0].logprobs.content
    conf   = LOG_HANDLER.process_logprobs(LOG_HANDLER.format_logprobs(tokens))
    skills = SKILL_DF.loc[[reply[k] for k in sorted(reply)], "Skill"].tolist()
    app.logger.info("Skill confidences: %s", conf)
    return skills

# ─── Allowed-file helper ──────────────────────────────────────────────────
def allowed(fname: str, exts: set[str]) -> bool:
    return "." in fname and fname.rsplit(".", 1)[1].lower() in exts

# ─── Routes ───────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    return render_template_string(HTML_PAGE)

@app.route("/ask", methods=["POST"])
def ask():
    prompt = request.form.get("prompt","").strip()
    if not prompt:
        return render_template_string(HTML_PAGE, answer="Please enter a prompt.")
    
    media = request.files.get("media")
    # ----- IMAGE -----------------------------------------------------------
    if media and allowed(media.filename, ALLOWED_IMG):
        try:
            url   = upload_image(media)
            parts = [{"type":"text","text":prompt},
                     {"type":"image_url","image_url":{"url":url}}]
            resp  = client.chat.completions.create(
                model=IMAGE_MODEL,
                messages=[{"role":"user","content":parts}],
                temperature=0.7)
            answer = resp.choices[0].message.content.strip()
        except Exception as e:
            answer = f"Error: {e}"
        return render_template_string(HTML_PAGE, answer=answer)

    # ----- VIDEO  (pipeline) ----------------------------------------------
    if media and allowed(media.filename, ALLOWED_VID):
        try:
            # 1) thumbnails → summary
            thumb_urls = extract_thumbnails(media)
            summary    = summarize_frames(prompt, thumb_urls)

            # 2) transcript via Whisper
            media.stream.seek(0)                     # rewind
            audio_tmp   = extract_audio_to_tmp(media)
            transcript  = whisper_transcribe(audio_tmp)
            audio_tmp.parent.unlink(missing_ok=True)

            # 3) skill labeling
            entry = {
                "title"       : secure_filename(media.filename),
                "transcript"  : transcript,
                "summary"     : summary,
            }
            skills = label_skills(entry)

            answer  = (
                f"**Summary**\n{summary}\n\n"
                f"**Top skills**: {', '.join(skills)}\n\n"
                f"**Transcript (first 400 chars)**\n{transcript[:400]}…"
            )
        except Exception as e:
            answer = f"Pipeline error: {e}"
        return render_template_string(HTML_PAGE, answer=answer)

    # ----- Text-only prompt ------------------------------------------------
    try:
        resp = client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[{"role":"user","content":prompt}],
            temperature=0.7)
        answer = resp.choices[0].message.content.strip()
    except Exception as e:
        answer = f"Error: {e}"
    return render_template_string(HTML_PAGE, answer=answer)

# ─── Entry point for local dev ─────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
