# app.py  ────────────────────────────────────────────────────────────────────
from __future__ import annotations
import os, uuid, tempfile, shutil, subprocess, json
from pathlib import Path

import boto3, pandas as pd
from werkzeug.utils import secure_filename
from moviepy.editor import VideoFileClip
from flask import Flask, request, render_template_string
from openai import OpenAI
from llm_confidence.logprobs_handler import LogprobsHandler

# ─── Runtime / env config ──────────────────────────────────────────────────
ALLOWED_IMG = {"png", "jpg", "jpeg", "gif"}
ALLOWED_VID = {"mp4", "mov", "webm", "mkv", "avi"}
BUCKET      = os.getenv("UPLOAD_BUCKET")
REGION      = os.getenv("AWS_REGION", "us-west-2")
SKILL_CSV   = os.getenv("SKILL_DEF_PATH", "resources/skill_definitions.csv")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-4o-mini")
AUDIO_MODEL = os.getenv("AUDIO_MODEL", "whisper-1")
TEXT_MODEL  = os.getenv("TEXT_MODEL", "deepseek-chat")
FRAMES      = 4

client  = OpenAI()                      # needs OPENAI_API_KEY
s3      = boto3.client("s3", region_name=REGION)
SKILL_DF= pd.read_csv(SKILL_CSV).rename(columns=lambda c: c.strip()).reset_index(drop=True)
LOG_HDL = LogprobsHandler()

# ─── Flask basics ──────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

HTML_PAGE = """
<!doctype html><html><head><meta charset="utf-8">
<title>ChatGPT + Image/Video</title>
<style>body{font-family:sans-serif;margin:2rem}
input[type=text],input[type=file]{width:60%;padding:.5rem}
button{padding:.5rem 1rem}pre{background:#f6f8fa;padding:1rem;border-radius:4px}</style>
</head><body>
<h1>Ask ChatGPT – optional image/video</h1>
<form action="/ask" method="post" enctype="multipart/form-data">
  <p><input name="prompt" placeholder="Enter your question" required></p>
  <p><input type="file" name="media" accept="image/*,video/*"></p>
  <button type="submit">Ask</button>
</form>
{% if answer %}<h2>Answer:</h2><pre>{{ answer }}</pre>{% endif %}
</body></html>
"""

# ─── helpers ----------------------------------------------------------------
def s3_put(buf, key, mime):
    s3.upload_fileobj(buf, BUCKET, key, ExtraArgs={"ContentType": mime})
    return s3.generate_presigned_url("get_object",
        Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=7*24*3600)

def upload_image(fs):
    ext = fs.filename.rsplit(".",1)[1].lower()
    return s3_put(fs, f"uploads/{uuid.uuid4()}.{ext}", fs.mimetype)

def allowed(fn:str, exts:set[str]) -> bool:
    return fn and "." in fn and fn.rsplit(".",1)[1].lower() in exts

def thumbnails(fs, n=FRAMES):
    tmp=tempfile.mkdtemp(); raw=Path(tmp,"video"); fs.save(raw)
    try:
        dur=float(json.loads(subprocess.check_output(
            ["ffprobe","-v","error","-select_streams","v","-show_entries",
             "format=duration","-of","json",raw]))["format"]["duration"])
    except Exception: dur=0
    fps=f"fps={n/dur}" if dur else "fps=1"
    subprocess.run(["ffmpeg","-i",raw,"-vf",f"{fps},scale=640:-1",
                    "-vframes",str(n),"-q:v","2",Path(tmp,"%02d.jpg")],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    urls=[]
    for jpg in sorted(Path(tmp).glob("*.jpg")):
        with open(jpg,"rb") as fh:
            urls.append(s3_put(fh,f"uploads/{uuid.uuid4()}.jpg","image/jpeg"))
    shutil.rmtree(tmp,ignore_errors=True)
    return urls

def audio_mp3(fs) -> Path:
    tmp=tempfile.mkdtemp(); raw=Path(tmp,"raw"); fs.save(raw)
    mp3=Path(tmp,"audio.mp3")
    VideoFileClip(str(raw)).audio.write_audiofile(mp3, logger=None)  # ← cast to str
    return mp3

def summarize(prompt, urls):
    parts=[{"type":"text","text":prompt}]+[
        {"type":"image_url","image_url":{"url":u}} for u in urls]
    r=client.chat.completions.create(model=IMAGE_MODEL,
        messages=[{"role":"user","content":parts}],temperature=0.7)
    return r.choices[0].message.content.strip()

def transcribe(mp3:Path):
    with open(mp3,"rb") as f:
        return client.audio.transcriptions.create(
            model=AUDIO_MODEL,file=f,response_format="text")

def tag_skills(entry):
    system=("You are an expert skill-tagger.\n\n"+
            "; ".join(f"(id:{i},label:{n})" for i,n in SKILL_DF["Skill"].items())+
            '\n\nReturn JSON {"label_1":id,…}')
    chat=client.chat.completions.create(model=TEXT_MODEL,
        messages=[{"role":"system","content":system},
                  {"role":"user","content":"\n".join(f"{k}:{entry[k]}" for k in entry)}],
        response_format={"type":"json_object"})
    ids=json.loads(chat.choices[0].message.content).values()
    return SKILL_DF.loc[list(ids),"Skill"].tolist()

# ─── routes ----------------------------------------------------------------
@app.route("/", methods=["GET"])
def home(): return render_template_string(HTML_PAGE)

@app.route("/ask", methods=["POST"])
def ask():
    prompt=request.form.get("prompt","").strip()
    if not prompt: return render_template_string(HTML_PAGE, answer="Need a prompt.")
    media=request.files.get("media")

    # image
    if media and allowed(media.filename, ALLOWED_IMG):
        try: answer=summarize(prompt,[upload_image(media)])
        except Exception as e: answer=f"Error: {e}"
        return render_template_string(HTML_PAGE, answer=answer)

    # video
    if media and allowed(media.filename, ALLOWED_VID):
        try:
            summary = summarize(prompt, thumbnails(media))
            media.stream.seek(0)
            mp3      = audio_mp3(media)
            transcript = transcribe(mp3)
            shutil.rmtree(mp3.parent, ignore_errors=True)
            labels = tag_skills({
                "title":secure_filename(media.filename),
                "transcript":transcript,
                "summary":summary})
            answer=(f"**Summary**\n{summary}\n\n"
                    f"**Top skills**: {', '.join(labels)}\n\n"
                    f"**Transcript (first 400 chars)**\n{transcript[:400]}…")
        except Exception as e:
            answer=f"Pipeline error: {e}"
        return render_template_string(HTML_PAGE, answer=answer)

    # text
    try:
        chat=client.chat.completions.create(
            model=TEXT_MODEL,messages=[{"role":"user","content":prompt}],temperature=0.7)
        answer=chat.choices[0].message.content.strip()
    except Exception as e:
        answer=f"Error: {e}"
    return render_template_string(HTML_PAGE, answer=answer)

if __name__=="__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
