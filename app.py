from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def index():
    return jsonify(message="Hello from Flask on AWS!")

if __name__ == "__main__":
    # Running locally?  ->  python app.py  ( http://127.0.0.1:8000 )
    app.run(host="0.0.0.0", port=8000, debug=True)