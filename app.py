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

# Logging setup
logging.basicConfig(level=logging.INFO)

# MongoDB
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["SAANBOT"]

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama3-8b-8192"

# In-memory session tracker
session_memory = {}

# Helper to extract lead details
def extract_lead_info(text):
    name_match = re.search(r"(?:name\s*is|I'm|I am)\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+)+)", text, re.I)
    phone_match = re.search(r"\b(\+91[\s\-]?\d{10}|\d{10})\b", text)
    email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text)
    return {
        "name": name_match.group(1) if name_match else None,
        "phone": phone_match.group(1) if phone_match else None,
        "email": email_match.group(0) if email_match else None
    }

@app.route("/")
def index():
    return "✅ SAANBOT backend is running.", 200

@app.route("/ask", methods=["POST"])
def ask():
    try:
        payload = request.get_json(force=True)
        question = payload.get("query", "").strip()
        session_id = payload.get("session_id", "unknown")
        user_id = payload.get("user_id", "anonymous")

        if not question:
            return jsonify({"response": "❗Please enter a valid question."}), 400

        # Setup session memory
        if session_id not in session_memory:
            session_memory[session_id] = {"name": None, "phone": None, "email": None}

        session_info = session_memory[session_id]

        # Load company data
        data = {}
        for collection in ["company_info", "services", "contacts", "awards", "brands", "products"]:
            try:
                data[collection] = list(db[collection].find({}, {"_id": 0}))
            except:
                data[collection] = []

        services = data.get("services", [])
        services_list = "\n".join([f"- {s['name']} ({s.get('description', '')})" for s in services])
        products = data.get("products", [])
        product_list = "\n".join([f"- {p['name']} | Brand: {p['brand']} | Category: {p['category']} | ₹{p['price_inr']} | Notes: {p['notes']}" for p in products]) or "No products listed."

        company = data.get("company_info", [{}])[0]
        about = company.get("about", "Not available")
        vision = company.get("vision", "Not available")
        founded = company.get("founded_year", "Not available")
        hq = company.get("headquarters", "Not available")
        address = company.get("address", "Not available")
        company_phone = company.get("phone", "Not available")
        contact = company.get("contact_person", {})
        contact_name = contact.get("name", "Srinivas Perur Varda")
        contact_email = contact.get("email", "varda@saanpro.com")
        contact_phone = contact.get("phone", company_phone)
        awards = "\n".join(f"- {a}" for a in company.get("awards", [])) or "None listed"
        brands = "\n".join(f"- {b}" for b in company.get("brands", [])) or "None listed"

        # Get message history
        history_cursor = db["chatlogs"].find({"metadata.session_id": session_id}, {"_id": 0, "query": 1, "response": 1}).sort("timestamp", -1).limit(3)
        history = list(history_cursor)[::-1]
        message_history = [{"role": "system", "content": "You are a helpful AI assistant."}]
        for msg in history:
            message_history.append({"role": "user", "content": msg["query"]})
            message_history.append({"role": "assistant", "content": msg["response"]})
        message_history.append({"role": "user", "content": question})

        # Add full context
        company_context = f"""
You are SAANBOT, a professional AI assistant for SAAN Protocol Experts Pvt. Ltd.

If user hasn't yet provided their name, phone, or email, ask them gently.
Once all 3 are received, greet them by name like "Hi {session_info['name']}!".

Company Details:
- About: {about}
- Vision: {vision}
- Founded: {founded}
- Headquarters: {hq}
- Address: {address}
- Phone: {company_phone}

Contact Person:
- Name: {contact_name}
- Phone: {contact_phone}
- Email: {contact_email}

Awards:
{awards}

Brands:
{brands}

Services:
{services_list}

Products:
{product_list}

🛒 If user wants to buy:
Also show this at the end:
🔗 https://merry-klepon-368950.netlify.app/

💡 Tell them to contact us directly for best pricing and tailored service.
"""
        message_history.insert(0, {"role": "system", "content": company_context})

        # Send to Groq
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": GROQ_MODEL,
                "messages": message_history
            },
            timeout=30
        )

        data = res.json()
        if "choices" not in data:
            raise ValueError("Groq response invalid")

        reply = data["choices"][0]["message"]["content"]

        # Detect and store contact info
        lead_info = extract_lead_info(question)
        updated = False
        for key in ["name", "phone", "email"]:
            if lead_info[key] and not session_info[key]:
                session_info[key] = lead_info[key]
                updated = True

        # Save as lead if all info known
        if updated and session_info["phone"] and session_info["email"]:
            db["leads"].insert_one({
                "name": session_info["name"] or "Unknown",
                "email": session_info["email"],
                "phone": session_info["phone"],
                "message": question,
                "timestamp": datetime.utcnow().isoformat(),
                "source": "SAANBOT"
            })

        # Save chat
        db["chatlogs"].insert_one({
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "query": question,
            "response": reply,
            "source_collections": ["company_info", "services", "contacts", "awards", "brands", "products"],
            "metadata": {
                "ip": request.remote_addr,
                "platform": "web",
                "session_id": session_id
            }
        })

        return jsonify({"response": reply})

    except Exception as e:
        logging.exception("Chatbot error")
        return jsonify({"response": "❌ Error occurred. Please contact Srinivas Perur Varda at +91 9342659932 or visit www.saanpro.com."}), 500

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=10000)
