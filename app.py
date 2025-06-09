from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import requests
import os
from dotenv import load_dotenv

# ====== Load Environment Variables ======
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama3-70b-8192"

# ====== Initialize App and DB ======
app = Flask(__name__)
CORS(app)
client = MongoClient(MONGO_URI)
db = client["SAANBOT"]

# ====== Helper: Ask Groq ======
def ask_groq(system_prompt, user_query):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            { "role": "system", "content": system_prompt },
            { "role": "user", "content": user_query }
        ],
        "temperature": 0.4
    }
    res = requests.post(url, headers=headers, json=payload)
    res.raise_for_status()
    return res.json()["choices"][0]["message"]["content"]

# ====== Route: /ask ======
@app.route("/ask", methods=["POST"])
def handle_query():
    user_query = request.json.get("query", "")

    # Fetch from all relevant collections
    data = {}
    for collection in ["company_info", "contacts", "services", "awards", "brands", "products"]:
        data[collection] = list(db[collection].find({}, {"_id": 0}))

    # System Prompt for Groq
    system_prompt = f"""
You are SAANBOT, the official chatbot for SAAN Protocol Experts Pvt Ltd.

You can answer questions about:
- Company profile and history
- Key contacts
- Awards and recognitions
- Services and solutions offered
- Associated brands and featured products

Here is the current database content:
{data}

Reply as a helpful professional assistant. If info is missing, say 'I don't have that information right now.'
"""

    try:
        answer = ask_groq(system_prompt, user_query)
        return jsonify({ "response": answer })
    except Exception as e:
        return jsonify({ "error": str(e) }), 500

# ====== Main ======
if __name__ == "__main__":
    app.run(debug=True)
