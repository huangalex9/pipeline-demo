from flask import Flask, request, render_template_string
import os
import openai

# Expect your OpenAI key to be set as an environment variable on the instance
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)

INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Ask ChatGPT</title>
  <style>
    body {font-family: sans-serif; margin: 2rem;}
    input[type=text] {width: 60%; padding: .5rem; font-size: 1rem;}
    button {padding: .5rem 1rem; font-size: 1rem; margin-left: .5rem;}
    pre {background: #f6f8fa; padding: 1rem; border-radius: 4px; white-space: pre-wrap;}
  </style>
</head>
<body>
  <h1>Ask ChatGPT</h1>
  <form action="/ask" method="post">
    <input type="text" name="prompt" placeholder="Enter your question" required />
    <button type="submit">Ask</button>
  </form>
  {% if answer %}
  <h2>Answer:</h2>
  <pre>{{ answer }}</pre>
  {% endif %}
</body>
</html>
"""

@app.route("/", methods=["GET"])
def index():
    """Serve the homepage with an input textbox."""
    return render_template_string(INDEX_HTML)

@app.route("/ask", methods=["POST"])
def ask():
    """Handle the form submit, call OpenAI, return the same page with the answer."""
    prompt = request.form.get("prompt", "").strip()
    if not prompt:
        return render_template_string(INDEX_HTML, answer="Please enter a prompt.")

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",  # adjust to the model you have access to
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        answer = response.choices[0].message.content.strip()
    except Exception as err:
        answer = f"Error: {err}"

    return render_template_string(INDEX_HTML, answer=answer)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)