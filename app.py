from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import os
import requests
import logging
from datetime import datetime
import re

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

def extract_lead_info(text):
    name_match = re.search(r"\b(?:name\s*is|I'm|I am)\s*([A-Z][a-z]+\s[A-Z][a-z]+)", text, re.I)
    phone_match = re.search(r"\b(\+91[\s\-]?\d{10}|\d{10})\b", text)
    email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text)
    return {
        "name": name_match.group(1) if name_match else None,
        "phone": phone_match.group(1) if phone_match else None,
        "email": email_match.group(0) if email_match else None
    }

@app.route("/ask", methods=["POST"])
def ask():
    try:
        payload = request.get_json(force=True)
        question = payload.get("query", "").strip()

        if not question:
            return jsonify({"response": "❗Please enter a valid question."}), 400

        # Load data from MongoDB
        data = {}
        for collection in ["company_info", "services", "contacts", "awards", "brands", "products"]:
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

        # Format product list
        products = data.get("products", [])
        product_list = "\n".join([
            f"- {p.get('name')} | Brand: {p.get('brand')} | Category: {p.get('category')} | ₹{p.get('price_inr')} | Notes: {p.get('notes')}"
            for p in products
        ]) or "No products listed."

        # Format company_info fields
        company = data.get("company_info", [{}])[0]
        about = company.get("about", "Not available")
        vision = company.get("vision", "Not available")
        founded = company.get("founded_year", "Not available")
        hq = company.get("headquarters", "Not available")
        address = company.get("address", "Not available")
        company_phone = company.get("phone", "Not available")
        awards = "\n".join(f"- {a}" for a in company.get("awards", [])) or "None listed"
        brands = "\n".join(f"- {b}" for b in company.get("brands", [])) or "None listed"

        prompt = f"""
You are SAANBOT, a professional AI assistant for SAAN Protocol Experts Pvt. Ltd.

Company Information:
- About: {about}
- Vision: {vision}
- Founded Year: {founded}
- Headquarters: {hq}
- Address: {address}
- Phone: {company_phone}

Awards:
{awards}

Brands We Work With:
{brands}

Services Offered:
{services_list or "No services data available."}

Available Products:
{product_list}

User's Question: {question}

Important Instruction:
If the question appears to be a sales inquiry or request for service, ask the user for their name, phone number, and email so our team can reach out.

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

        # ✅ Save chat to 'chatlogs'
        try:
            db["chatlogs"].insert_one({
                "user_id": payload.get("user_id", "anonymous"),
                "timestamp": datetime.utcnow().isoformat(),
                "query": question,
                "response": reply,
                "source_collections": list(data.keys()),
                "metadata": {
                    "ip": request.remote_addr,
                    "platform": "web",
                    "session_id": payload.get("session_id", "unknown")
                }
            })
        except Exception as log_err:
            logging.warning(f"⚠️ Failed to log chat: {log_err}")

        # ✅ Check and save lead if contact info is present
        lead_info = extract_lead_info(question)
        if lead_info["phone"] and lead_info["email"]:
            try:
                db["leads"].insert_one({
                    "name": lead_info["name"] or "Unknown",
                    "email": lead_info["email"],
                    "phone": lead_info["phone"],
                    "message": question,
                    "timestamp": datetime.utcnow().isoformat(),
                    "source": "SAANBOT"
                })
                logging.info("✅ Lead captured in MongoDB.")
            except Exception as e:
                logging.warning(f"⚠️ Failed to save lead: {e}")

        return jsonify({"response": reply})

    except Exception as e:
        logging.exception("Error during processing")
        return jsonify({
            "response": "❌ An error occurred while fetching the answer. Please contact Srinivas Perur Varda at +91 9342659932 or visit www.saanpro.com."
        }), 500

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=10000)
