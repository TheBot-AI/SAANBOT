from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import requests
import os

# === CONFIG ===
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama3-70b-8192"
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "SAANBOT"

# === INIT ===
app = Flask(__name__)
CORS(app)
client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# === GROQ PROMPT FUNCTION ===
def ask_groq(system_prompt, user_query):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ],
        "temperature": 0.4
    }
    res = requests.post(url, headers=headers, json=payload)
    return res.json()["choices"][0]["message"]["content"]

# === ROUTE: /ask ===
@app.route("/ask", methods=["POST"])
def handle_query():
    user_input = request.json.get("query", "")

    # Fetch all data from MongoDB
    info = {col: list(db[col].find({}, {"_id": 0})) for col in [
        "company_info", "contacts", "services", "awards", "brands", "products"
    ]}

    # Build system prompt
    system_prompt = f"""
You are SAANBOT, the official assistant for SAAN Protocol Experts Pvt Ltd.
You can answer queries about the company, services, awards, contact info, and product offerings.

Here is the company's data:
{info}

Answer user queries truthfully and concisely in a friendly, professional tone.
"""

    answer = ask_groq(system_prompt, user_input)
    return jsonify({"response": answer})

# === MAIN ===
if __name__ == "__main__":
    app.run(debug=True)
