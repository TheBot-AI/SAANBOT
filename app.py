from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import os
import requests

app = Flask(__name__)
CORS(app)

# MongoDB connection (environment variable)
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["SAANBOT"]

# Groq API
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "mixtral-8x7b-32768"

@app.route("/")
def home():
    return "SAANBOT is live!"

@app.route("/ask", methods=["POST"])
def handle_query():
    try:
        question = request.json.get("query", "").strip()
        if not question:
            return jsonify({"response": "Please enter a valid question."}), 400

        collections = ["company_info", "services", "contacts", "awards", "brands"]
        data = {}
        for collection in collections:
            data[collection] = list(db[collection].find({}, {"_id": 0}))

        # Format services into bullet points with descriptions
        services = [f"- {s.get('name')} ({s.get('description', 'No description')})" for s in data.get("services", [])]
        service_list = "\n".join(services)

        # Compose the prompt
        prompt = f"""
You are SAANBOT, a helpful and professional AI assistant working for SAAN Protocol Experts.

Based on the available data below, answer the user's question as clearly and helpfully as possible.

Available Services:
{service_list}

If the answer cannot be found in the provided data, politely say:
"I'm sorry, I couldn't find that specific detail in my current data. For more information, please contact Srinivas Perur Varda at +91 9342659932 or visit www.saanpro.com."

User's Question: {question}
"""

        # Call Groq API
        groq_response = requests.post(
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

        groq_data = groq_response.json()
        reply = groq_data["choices"][0]["message"]["content"]

        return jsonify({"response": reply})

    except Exception as e:
        print("Error:", e)
        return jsonify({
            "response": "I'm sorry, an error occurred while trying to fetch that information. Please contact Srinivas Perur Varda at +91 9342659932 or visit www.saanpro.com."
        }), 500

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=10000)
