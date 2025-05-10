from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

@app.route("/start-voice-assistant", methods=["POST"])
def start_voice_assistant():
    # Replace this with actual Gemini response logic
    return jsonify({"reply": "Hello from Gemini! Here's some information."})

if __name__ == "__main__":  # ✅ This block is essential!
    app.run(debug=True)
