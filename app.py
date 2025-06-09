from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import os
import requests

app = Flask(__name__)
CORS(app)

# MongoDB connection from environment
MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["SAANBOT"]

collections = ["company_info", "services", "contacts", "brands", "awards"]

@app.route("/")
def home():
    return "✅ SAANBOT is running."

@app.route("/ask", methods=["POST"])
def handle_query():
    try:
        user_question = request.json.get("question")
        if not user_question:
            return jsonify({"response": "❌ Please enter a question."}), 400

        # Fetch knowledge base
        data = {}
        for collection in collections:
            try:
                data[collection] = list(db[collection].find({}, {"_id": 0}))
            except Exception:
                data[collection] = []

        # Ask Groq
        groq_key = os.environ.get("GROQ_API_KEY")
        if not groq_key:
            return jsonify({"response": "❌ GROQ_API_KEY missing."}), 500

        prompt = f"""
You are SAANBOT, the official AI assistant for SAAN Protocol Experts.
Answer based only on the data below:

Company Info: {data.get("company_info", [])}
Services: {data.get("services", [])}
Contacts: {data.get("contacts", [])}
Brands: {data.get("brands", [])}
Awards: {data.get("awards", [])}

User Question: "{user_question}"
"""

        groq_response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {groq_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama3-8b-8192",
                "messages": [
                    {"role": "system", "content": "You are a helpful company assistant."},
                    {"role": "user", "content": prompt}
                ]
            }
        )

        if groq_response.status_code != 200:
            return jsonify({"response": "❌ Groq AI error."}), 500

        reply = groq_response.json()["choices"][0]["message"]["content"]
        return jsonify({"response": reply})

    except Exception as e:
        return jsonify({
            "response": f"❌ Server error: {str(e)}"
        }), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
