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

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama3-8b-8192"

# Helper: extract name/phone/email
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
        user_id = payload.get("user_id", "anonymous")
        session_id = payload.get("session_id", "unknown")

        if not question:
            return jsonify({"response": "❗Please enter a valid question."}), 400

        # Load collections
        data = {}
        for collection in ["company_info", "services", "contacts", "awards", "brands", "products"]:
            try:
                data[collection] = list(db[collection].find({}, {"_id": 0}))
            except Exception as db_err:
                logging.warning(f"Could not fetch collection '{collection}': {db_err}")
                data[collection] = []

        # Format services
        services = data.get("services", [])
        services_list = "\n".join([
            f"- {s.get('name')} ({s.get('description', 'No description')})"
            for s in services
        ])

        # Format products
        products = data.get("products", [])
        product_list = "\n".join([
            f"- {p.get('name')} | Brand: {p.get('brand')} | Category: {p.get('category')} | ₹{p.get('price_inr')} | Notes: {p.get('notes')}"
            for p in products
        ]) or "No products listed."

        # Company info
        company = data.get("company_info", [{}])[0]
        about = company.get("about", "Not available")
        vision = company.get("vision", "Not available")
        founded = company.get("founded_year", "Not available")
        hq = company.get("headquarters", "Not available")
        address = company.get("address", "Not available")
        company_phone = company.get("phone", "Not available")
        awards = "\n".join(f"- {a}" for a in company.get("awards", [])) or "None listed"
        brands = "\n".join(f"- {b}" for b in company.get("brands", [])) or "None listed"

        # Fetch contact person
        contact = company.get("contact_person", {})
        contact_name = contact.get("name", "Srinivas Perur Varda")
        contact_email = contact.get("email", "varda@saanpro.com")
        contact_phone = contact.get("phone", company_phone)
        contact_block = f"""
Contact Person:
- Name: {contact_name}
- Phone: {contact_phone}
- Email: {contact_email}
"""

        # Fetch last 3 messages from chatlogs for session
        history_cursor = db["chatlogs"].find(
            {"metadata.session_id": session_id},
            {"_id": 0, "query": 1, "response": 1}
        ).sort("timestamp", -1).limit(3)
        history = list(history_cursor)[::-1]

        message_history = [{"role": "system", "content": "You are a helpful AI assistant."}]
        for msg in history:
            message_history.append({"role": "user", "content": msg["query"]})
            message_history.append({"role": "assistant", "content": msg["response"]})
        message_history.append({"role": "user", "content": question})

        # Inject full context
        company_context = f"""
You are SAANBOT, a professional AI assistant for SAAN Protocol Experts Pvt. Ltd.

Company Information:
- About: {about}
- Vision: {vision}
- Founded Year: {founded}
- Headquarters: {hq}
- Address: {address}
- Phone: {company_phone}

{contact_block}

Awards:
{awards}

Brands We Work With:
{brands}

Services Offered:
{services_list or "No services data available."}

Available Products:
{product_list}

Important Instruction:
If the user asks to buy a product or shows purchase interest, always respond that the product is available **exclusively** through SAAN Protocol Experts Pvt. Ltd. Do not mention external retailers, e-commerce sites, or third-party platforms.

Use this format at the end of your reply:

"You can purchase this product directly from SAAN Protocol Experts Pvt. Ltd.

📍 Visit us at: {address}  
📞 Call us: {contact_phone}  
✉️ Email: {contact_email}

Our team will help you with pricing, availability, and delivery options."

If the user message is a business inquiry (like product/service request), politely ask for their name, phone number, and email. If they have already given it, continue without asking again.

If you don’t have the answer, respond with:
"I'm sorry, I couldn't find that specific detail in my current data. For more information, contact {contact_name} at {contact_phone} or visit www.saanpro.com."

"""
        message_history.insert(0, {"role": "system", "content": company_context})

        # Call Groq
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

        groq_data = res.json()
        if "choices" not in groq_data:
            raise ValueError("Missing 'choices' in Groq response")

        reply = groq_data["choices"][0]["message"]["content"]
        # Detect buying intent
        purchase_keywords = ["buy", "purchase", "quote", "get this", "interested in", "need this", "want this", "price of", "how much", "cost of"]
        if any(keyword in question.lower() for keyword in purchase_keywords):
            reply += """

🛒 Alternatively you can purchase products here:  
🔗 https://merry-klepon-368950.netlify.app/

💡 For **best pricing**, bulk orders, or personalized expert recommendations, please contact us directly:  
📞 +91 9342659932  
✉️ varda@saanpro.com

We offer better deals, faster support, and tailored solutions when you buy directly from SAAN Protocol Experts Pvt. Ltd. 💼
"""


        # Save chat
        db["chatlogs"].insert_one({
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "query": question,
            "response": reply,
            "source_collections": list(data.keys()),
            "metadata": {
                "ip": request.remote_addr,
                "platform": "web",
                "session_id": session_id
            }
        })

        # Check for contact info
        lead_info = extract_lead_info(question)
        if lead_info["phone"] and lead_info["email"]:
            db["leads"].insert_one({
                "name": lead_info["name"] or "Unknown",
                "email": lead_info["email"],
                "phone": lead_info["phone"],
                "message": question,
                "timestamp": datetime.utcnow().isoformat(),
                "source": "SAANBOT"
            })
            logging.info("✅ Lead captured in MongoDB.")

        return jsonify({"response": reply})

    except Exception as e:
        logging.exception("Error during processing")
        return jsonify({
            "response": "❌ An error occurred while fetching the answer. Please contact Srinivas Perur Varda at +91 9342659932 or visit www.saanpro.com."
        }), 500

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=10000)
