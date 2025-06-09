from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import os
import requests
import logging

app = Flask(__name__)
CORS(app)

# Setup logging
logging.basicConfig(level=logging.INFO)

# MongoDB setup
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["SAANBOT"]

# ✅ Use free-tier supported Groq model
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama3-8b-8192"

@app.route("/")
def index():
    return "✅ SAANBOT backend is running.", 200

@app.route("/ask", methods=["POST"])
def ask():
    try:
        payload = request.get_json(force=True)
        question = payload.get("query", "").strip()

        if not question:
            return jsonify({"response": "❗Please enter a valid question."}), 400

        # Load data from MongoDB
        data = {}
        for collection in ["company_info", "services", "contacts", "awards", "brands"]:
            try:
                data[collection] = list(db[collection].find({}, {"_id": 0}))
            except Exception as db_err:
                logging.warning(f"Could not fetch collection '{collection}': {db_err}")
                data[collection] = []

        # Format services if available
        services = data.get("services", [])
        services_list = "\n".join([
            f"- {s.get('name')} ({s.get('description', 'No description')})"
            for s in services
        ])

        prompt = f"""
You are SAANBOT, a professional AI assistant for SAAN Protocol Experts.

Below is the available company data:

Services Offered:
{services_list or "No services data available."}

User's Question: {question}

If the information cannot be found, reply with:
"I'm sorry, I couldn't find that specific detail in my current data. For more information, please contact Srinivas Perur Varda at +91 9342659932 or visit www.saanpro.com."
"""

        # Call Groq API
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a helpful AI assistant."},
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=30
        )

        groq_data = res.json()
        logging.info("Groq response: %s", groq_data)

        if "choices" not in groq_data:
            raise ValueError("Missing 'choices' in Groq response")

        reply = groq_data["choices"][0]["message"]["content"]
        return jsonify({"response": reply})

    except Exception as e:
        logging.exception("Error during processing")
        return jsonify({
            "response": "❌ An error occurred while fetching the answer. Please contact Srinivas Perur Varda at +91 9342659932 or visit www.saanpro.com."
        }), 500

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=10000)
