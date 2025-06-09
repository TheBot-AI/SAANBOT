from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import requests
import os
import certifi
from dotenv import load_dotenv

# ===== Load Environment Variables =====
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama3-70b-8192"

# ===== Initialize App and DB =====
app = Flask(__name__)
CORS(app)

client = MongoClient(
    MONGO_URI,
    tls=True,
    tlsCAFile=certifi.where()
)
db = client["SAANBOT"]

# ====== Route: Health Check ======
@app.route("/")
def home():
    return "SAANBOT is live 🚀", 200

@app.route("/health")
def health():
    return "✅ SAANBOT is healthy", 200

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
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

# ====== Main Chat Route ======
@app.route("/ask", methods=["POST"])
def handle_query():
    user_query = request.json.get("query", "").strip()
    if not user_query:
        return jsonify({ "error": "No query provided." }), 400

    try:
        # Fetch all relevant collections
        data = {}
        for collection in ["company_info", "contacts", "services", "awards", "brands", "products"]:
            data[collection] = list(db[collection].find({}, {"_id": 0}))

        # Build system prompt
        system_prompt = f"""
You are SAANBOT, a helpful assistant for SAAN Protocol Experts Pvt Ltd.

You answer questions about:
- Company background and services
- Contact details of key personnel
- Awards and recognitions
- Services like AV, signage, VC
- Brands associated (e.g., Sony, Samsung)
- Products available (if any listed)

Use only this database content to answer:
{data}

If information is missing, say "I'm sorry, I don't have that detail at the moment."
"""

        reply = ask_groq(system_prompt, user_query)
        return jsonify({ "response": reply })

    except Exception as e:
        return jsonify({ "error": str(e) }), 500

# ====== Run ======
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
