🎥 Skill Tagging from Video using AWS CodePipeline & Flask
This project enables automatic skill tagging of educational videos through a fully-deployed AWS pipeline. It combines video summarization, transcription, and LLM-based tagging, and is powered by a Flask-based web UI hosted on an EC2 instance.

🚀 Overview
This application allows users to upload videos via a web interface. The backend uses a combination of image snapshots and audio transcription to:

Generate a summary of the video using OpenAI's GPT and Whisper models.

Perform skill tagging by matching the content to a CSV of predefined skills.

Display all outputs in a clean, single-page Flask UI.

Store all uploads in an S3 bucket.

Deployment is handled by AWS CodePipeline, which:

Uses this GitHub repository as the source.

Triggers CodeDeploy to set up and run the Flask app on EC2.

Automatically redeploys the server on every GitHub commit.

🧠 Key Features
Flask Web Interface – Upload videos, enter a prompt, and view results directly in the browser.

S3 Integration – Uploaded media and generated thumbnails are stored and retrieved via S3.

Video-to-Text Processing – Extracts audio using moviepy and transcribes using OpenAI Whisper.

Image-Based Summarization – Captures key video frames for visual summarization using OpenAI GPT-4o.

LLM-based Skill Tagging – Tags videos with relevant skills using a curated CSV file and GPT model.

CI/CD with AWS CodePipeline – Fully automated deployments with GitHub + EC2 + CodeDeploy.

🗂️ File Structure
File / Dir	Purpose
app.py	Core Flask application: handles uploads, summarization, transcription, tagging
appspec.yml	CodeDeploy specification for deployment hooks
buildspec.yml	CodePipeline build script (archives app for deployment)
constants.py	Contains the default prompt used in summarization
index.html	HTML template (inline in app.py) for the web UI
requirements.txt	Python dependencies
testing.sh	Shell script for basic testing / local setup
scripts/	Deployment lifecycle scripts (install, start, stop)

🔧 Deployment Pipeline
Source – GitHub repository

Build – Compresses the repo into app.zip

Deploy – CodeDeploy:

Installs dependencies

Starts the Flask server via gunicorn

Stops/restarts on new deployments

EC2 Setup Notes:
Flask runs on port 8000

Server is served using gunicorn

Deployment hooks defined in scripts/start_server.sh, etc.

🧪 Usage
Open the app in your browser.

Enter a prompt or use the default.

Upload an image or video file.

View the output:

Summary

Skill tags (up to 5)

Transcript (first 400 chars)

📦 Sample Skill Tag Output
text
Copy
Edit
**Summary**
This video explains how machine learning models make predictions based on input data.

**Skills**: Supervised Learning, Feature Engineering, Model Evaluation

**Transcript (first 400 chars)**
In this video, we explore the foundations of machine learning and discuss the pipeline used for training models...
📚 Requirements
Install dependencies with:

bash
Copy
Edit
pip install -r requirements.txt
Or set up a virtual environment for development.

🛠 Future Improvements
Add login/authentication

Visualize skill definitions on UI

Support batch uploads

Add more advanced fallback for model errors

📬 Contact
For questions or collaborations, please contact the team via [your-email@example.com] or file an issue in the repo.

