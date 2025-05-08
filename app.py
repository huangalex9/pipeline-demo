# app.py  ────────────────────────────────────────────────────────────────────
from __future__ import annotations
import os, uuid, tempfile, shutil, subprocess, json
from pathlib import Path
import boto3, pandas as pd
from werkzeug.utils import secure_filename
from moviepy.editor import VideoFileClip
from flask import Flask, request, render_template_string
from openai import OpenAI, NotFoundError
from llm_confidence.logprobs_handler import LogprobsHandler
from constants import DEFAULT_PROMPT

# ─── ENV / CONFIG ──────────────────────────────────────────────────────────
ALLOWED_IMG = {"png","jpg","jpeg","gif"}
ALLOWED_VID = {"mp4","mov","webm","mkv","avi"}
BUCKET      = os.getenv("UPLOAD_BUCKET")
REGION      = os.getenv("AWS_REGION","us-west-2")
SKILL_CSV   = os.getenv("SKILL_DEF_PATH","resources/skill_definitions.csv")
IMAGE_MODEL = os.getenv("IMAGE_MODEL","gpt-4o-mini")
AUDIO_MODEL = os.getenv("AUDIO_MODEL","whisper-1")
# TEXT_MODEL  = os.getenv("TEXT_MODEL","gpt-3.5-turbo")
TEXT_MODEL = "gpt-4.1-nano"
FALLBACK_TEXT_MODEL = "gpt-4.1-nano"
FRAMES = 4

client  = OpenAI()
s3      = boto3.client("s3", region_name=REGION)
SKILLS  = pd.read_csv(SKILL_CSV).rename(columns=lambda c:c.strip()).reset_index(drop=True)
LOG     = LogprobsHandler()

# ─── Flask UI ----------------------------------------------------------------
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024

PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>SAAS Delta Project</title>
<style>
  body   {font-family:sans-serif; margin:2rem;}
  input[type=text], input[type=file] {width:60%; padding:.5rem;}
  button {padding:.5rem 1rem;}
  /* --- keep answers inside the viewport --- */
  pre {
    background:#f6f8fa; padding:1rem; border-radius:4px;
    white-space:pre-wrap;      /* allow line-wrapping */
    word-wrap:break-word;      /* break long tokens/URLs */
    overflow-x:auto;           /* show a scroll bar if it’s STILL too wide */
    max-width: 100%;           /* never exceed the parent width */
  }
  textarea {width:60%; height:6rem; resize:vertical;}   /* optional: larger prompt box */
</style>
</head><body>
<h1>Delta x SAAS Project – Skill Tagging in Video Data</h1>
<form action="/ask" method="post" enctype="multipart/form-data">
  <p><textarea name="prompt" placeholder="Enter prompt or [default_prompt]" required></textarea></p>
  <p><input type="file" name="media" accept="image/*,video/*"></p>
  <button type="submit">Ask</button>
</form>
{% if answer %}
  <h2>Answer:</h2><pre>{{ answer }}</pre>
{% endif %}
</body></html>"""

# ─── helpers -----------------------------------------------------------------
def s3_url(buf,key,mime):
    s3.upload_fileobj(buf, BUCKET, key, ExtraArgs={"ContentType":mime})
    return s3.generate_presigned_url("get_object",
        Params={"Bucket":BUCKET,"Key":key},ExpiresIn=604800)

def allowed(fn:str, exts:set[str])->bool:
    return fn and "." in fn and fn.rsplit(".",1)[1].lower() in exts

def thumbnails(fs, n=FRAMES):
    tmp=tempfile.mkdtemp(); raw=Path(tmp,"video"); fs.save(raw)
    dur=0
    try:
        dur=float(json.loads(subprocess.check_output(
            ["ffprobe","-v","error","-select_streams","v","-show_entries",
             "format=duration","-of","json",raw]))["format"]["duration"])
    except Exception: pass
    fps=f"fps={n/dur}" if dur else "fps=1"
    subprocess.run(["ffmpeg","-i",raw,"-vf",f"{fps},scale=640:-1",
                    "-vframes",str(n),"-q:v","2",Path(tmp,"%02d.jpg")],
                   check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    urls=[]
    for jpg in Path(tmp).glob("*.jpg"):
        with open(jpg,"rb") as fh:
            urls.append(s3_url(fh,f"uploads/{uuid.uuid4()}.jpg","image/jpeg"))
    shutil.rmtree(tmp,ignore_errors=True)
    return urls

def audio_mp3(fs)->Path:
    tmp=tempfile.mkdtemp(); raw=Path(tmp,"raw"); fs.save(raw)
    mp3=Path(tmp,"audio.mp3")
    VideoFileClip(str(raw)).audio.write_audiofile(mp3, logger=None)
    return mp3

def chat(model:str, **kw):
    try:
        return client.chat.completions.create(model=model, **kw)
    except NotFoundError:
        if model!=FALLBACK_TEXT_MODEL:
            return chat(FALLBACK_TEXT_MODEL, **kw)
        raise

def summarize(prompt,urls):
    parts=[{"type":"text","text":prompt}]+[
        {"type":"image_url","image_url":{"url":u}} for u in urls]
    r=chat(model=IMAGE_MODEL,messages=[{"role":"user","content":parts}],temperature=0.7)
    return r.choices[0].message.content.strip()

def transcribe(mp3:Path):
    with open(mp3,"rb") as f:
        return client.audio.transcriptions.create(
            model=AUDIO_MODEL,file=f,response_format="text")

def tag(entry:dict)->list[str]:
    system=("You are an expert skill-tagger. Identify up to 5 relevant skills. \n\n"+
            "; ".join(f"(id:{i},label:{row.Skill})" for i,row in SKILLS.iterrows())+
            '\n\nReturn JSON {"label_1":id,…}')
    resp=chat(model=TEXT_MODEL,
        messages=[{"role":"system","content":system},
                  {"role":"user","content":"\n".join(f"{k}:{entry[k]}" for k in entry)}],
        response_format={"type":"json_object"},temperature=0)
    try:
        raw_ids=json.loads(resp.choices[0].message.content).values()
    except Exception: return ["(invalid JSON)"]
    ids=[int(x) for x in raw_ids if str(x).isdigit() and 0<=int(x)<len(SKILLS)]
    return SKILLS.loc[ids,"Skill"].tolist() or ["(no valid ids)"]

# ─── routes -----------------------------------------------------------------
@app.route("/",methods=["GET"])
def home(): return render_template_string(PAGE)

@app.route("/ask",methods=["POST"])
def ask():
    prompt=request.form.get("prompt","").strip()
    media=request.files.get("media")
    if not prompt: return render_template_string(PAGE,answer="Need a prompt.")

    # image
    if media and allowed(media.filename, ALLOWED_IMG):
        try:
            url=s3_url(media,f"uploads/{uuid.uuid4()}.{media.filename.rsplit('.',1)[1].lower()}",media.mimetype)
            ans=summarize(prompt,[url])
        except Exception as e: ans=f"Error: {e}"
        return render_template_string(PAGE,answer=ans)

    # video
    if media and allowed(media.filename, ALLOWED_VID):
        try:
            if prompt=="[default_prompt]": prompt=DEFAULT_PROMPT
            summary=summarize(prompt,thumbnails(media))
            media.stream.seek(0)
            mp3=audio_mp3(media)
            transcript=transcribe(mp3)
            shutil.rmtree(mp3.parent,ignore_errors=True)
            skills=tag({"title":secure_filename(media.filename),
                        "transcript":transcript,"summary":summary})
            ans=(f"**Summary**\n{summary}\n\n"
                 f"**Skills**: {', '.join(skills)}\n\n"
                 f"**Transcript (first 400 chars)**\n{transcript[:400]}…")
        except Exception as e: ans=f"Pipeline error: {e}"
        return render_template_string(PAGE,answer=ans)

    # text
    try:
        chat_resp=chat(model=TEXT_MODEL,
            messages=[{"role":"user","content":prompt}],temperature=0.7)
        ans=chat_resp.choices[0].message.content.strip()
    except Exception as e: ans=f"Error: {e}"
    return render_template_string(PAGE,answer=ans)

if __name__=="__main__":
    app.run(host="0.0.0.0",port=8000,debug=True)
# skill tagging for video data is working (chekpoint)