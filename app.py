# app.py  ────────────────────────────────────────────────────────────────────
from __future__ import annotations
import os, uuid, tempfile, shutil, subprocess, json
from pathlib import Path

import cv2
import boto3, pandas as pd
from werkzeug.utils import secure_filename
from moviepy.editor import VideoFileClip
from flask import Flask, request, render_template_string
from openai import OpenAI
from llm_confidence.logprobs_handler import LogprobsHandler

# ─── env + price-control toggles ───────────────────────────────────────────
BUDGET_MODE   = os.getenv("BUDGET_MODE", "false").lower() == "true"

ALLOWED_IMG   = {"png","jpg","jpeg","gif"}
ALLOWED_VID   = {"mp4","mov","webm","mkv","avi"}
BUCKET        = os.getenv("UPLOAD_BUCKET")
REGION        = os.getenv("AWS_REGION","us-west-2")
SKILL_CSV     = os.getenv("SKILL_DEF_PATH","resources/skill_definitions.csv")

IMAGE_MODEL   = "gpt-4o-mini"                        # still needed for vision
AUDIO_MODEL   = None if BUDGET_MODE else "whisper-1"
TEXT_MODEL    = "gpt-3.5-turbo" if BUDGET_MODE else os.getenv("TEXT_MODEL","deepseek-chat")
FRAMES        = 1 if BUDGET_MODE else 4

# ─── clients / globals ─────────────────────────────────────────────────────
client  = OpenAI()
s3      = boto3.client("s3", region_name=REGION)
SKILL_DF= pd.read_csv(SKILL_CSV).rename(columns=lambda c: c.strip()).reset_index(drop=True)
LOG_HDL = LogprobsHandler()

# ─── Flask setup ───────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200*1024*1024   # 200 MB

HTML_PAGE = """
<!doctype html><html lang="en"><head><meta charset="UTF-8" />
<title>ChatGPT demo</title><style>body{font-family:sans-serif;margin:2rem}
input[type=text],input[type=file]{width:60%;padding:.5rem}button{padding:.5rem 1rem}
pre{background:#f6f8fa;padding:1rem;border-radius:4px;white-space:pre-wrap}</style>
</head><body>
<h1>Ask ChatGPT {% if budget %}(budget mode){% endif %}</h1>
<form action="/ask" method="post" enctype="multipart/form-data">
  <p><input type="text"  name="prompt" placeholder="Enter your question" required></p>
  <p><input type="file" name="media" accept="image/*,video/*"></p>
  <button type="submit">Ask</button>
</form>
{% if answer %}<h2>Answer:</h2><pre>{{answer}}</pre>{% endif %}
</body></html>"""

# ─── S3 helpers ────────────────────────────────────────────────────────────
def s3_put(fileobj,key,mime):
    s3.upload_fileobj(fileobj, BUCKET, key, ExtraArgs={"ContentType":mime})
    return s3.generate_presigned_url("get_object",
        Params={"Bucket":BUCKET,"Key":key},ExpiresIn=7*24*3600)

def upload_image(fs):
    ext = fs.filename.rsplit(".",1)[1].lower()
    return s3_put(fs, f"uploads/{uuid.uuid4()}.{ext}", fs.mimetype)

# ─── video helpers (thumb + audio) ─────────────────────────────────────────
def thumbnails(fs, n=FRAMES):
    tmp = tempfile.mkdtemp(); raw = Path(tmp,"v")
    fs.save(raw); outpat = Path(tmp,"f%02d.jpg")
    dur = 0
    try:
        meta=json.loads(subprocess.check_output(
            ["ffprobe","-v","error","-select_streams","v","-show_entries",
             "format=duration","-of","json",raw]))
        dur=float(meta["format"]["duration"])
    except Exception:pass
    fps=f"fps={n/dur}" if dur else "fps=1"
    subprocess.run(["ffmpeg","-i",raw,"-vf",f"{fps},scale=640:-1",
                    "-vframes",str(n),"-q:v","2",outpat],check=True,
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    urls=[]
    for jpg in sorted(Path(tmp).glob("f*.jpg")):
        with open(jpg,"rb") as fh:
            urls.append(s3_put(fh,f"uploads/{uuid.uuid4()}.jpg","image/jpeg"))
    shutil.rmtree(tmp,ignore_errors=True)
    return urls

def audio_mp3(fs)->Path|None:
    if AUDIO_MODEL is None: return None
    tmp=tempfile.mkdtemp(); raw=Path(tmp,"raw"); fs.save(raw)
    mp3=Path(tmp,"a.mp3"); VideoFileClip(raw).audio.write_audiofile(mp3,logger=None)
    return mp3

# ─── LLM wrappers ─────────────────────────────────────────────────────────-
def summarize(prompt,urls):
    parts=[{"type":"text","text":prompt}]+[
        {"type":"image_url","image_url":{"url":u}} for u in urls]
    r=client.chat.completions.create(model=IMAGE_MODEL,
        messages=[{"role":"user","content":parts}],temperature=0.2)
    return r.choices[0].message.content.strip()

def transcribe(mp3:Path)->str:
    with open(mp3,"rb") as f:
        return client.audio.transcriptions.create(
            model=AUDIO_MODEL,file=f,response_format="text")

def tag_skills(entry):
    system=("You are an expert skill-tagger. Return 3–5 ids only.\n\n"+
            "; ".join(f"(id:{i},label:{n})" for i,n in SKILL_DF["Skill"].items()))
    r=client.chat.completions.create(model=TEXT_MODEL,
        messages=[{"role":"system","content":system},
                  {"role":"user","content":"\n".join(f"{k}:{entry[k]}" for k in entry)}],
        response_format={"type":"json_object"})
    ids=json.loads(r.choices[0].message.content).values()
    return SKILL_DF.loc[list(ids),"Skill"].tolist()

# ─── Flask routes ──────────────────────────────────────────────────────────
@app.route("/",methods=["GET"])
def home(): return render_template_string(HTML_PAGE,budget=BUDGET_MODE)

@app.route("/ask",methods=["POST"])
def ask():
    prompt=request.form.get("prompt","").strip()
    media=request.files.get("media")
    if not prompt: return render_template_string(HTML_PAGE,answer="Need a prompt.",budget=BUDGET_MODE)

    # Image only (cheap)
    if media and media.filename and media.filename.split(".")[-1].lower() in ALLOWED_IMG:
        url=upload_image(media)
        ans=summarize(prompt,[url])
        return render_template_string(HTML_PAGE,answer=ans,budget=BUDGET_MODE)

    # Video pipeline (can be heavy)
    if media and media.filename and media.filename.split(".")[-1].lower() in ALLOWED_VID:
        thumbs=thumbnails(media)
        summary=summarize(prompt,thumbs)
        transcript="(skipped)" if AUDIO_MODEL is None else transcribe(audio_mp3(media))
        labels="(skipped)" if BUDGET_MODE else ", ".join(tag_skills(
            {"title":media.filename,"transcript":transcript,"summary":summary}))
        answer=f"**Summary**\n{summary}\n\n**Skills** {labels}\n\n**Transcript (first 300 chars)**\n{transcript[:300]}…"
        return render_template_string(HTML_PAGE,answer=answer,budget=BUDGET_MODE)

    # Text-only
    r=client.chat.completions.create(model=TEXT_MODEL,
        messages=[{"role":"user","content":prompt}],temperature=0.7)
    return render_template_string(HTML_PAGE,
        answer=r.choices[0].message.content.strip(),budget=BUDGET_MODE)

# ─── dev entry ─────────────────────────────────────────────────────────────
if __name__=="__main__":
    app.run(host="0.0.0.0",port=8000,debug=True)
