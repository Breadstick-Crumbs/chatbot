from flask import Flask, request
import requests
import openai
from woocommerce import API

# --- Configuration ---
 

# --- Initialize clients ---
wcapi = API(
    url=WOOCOMMERCE_URL,
    consumer_key=WOOCOMMERCE_CONSUMER_KEY,
    consumer_secret=WOOCOMMERCE_CONSUMER_SECRET,
    version="wc/v3"
)
openai.api_key = GPT_API_KEY

app = Flask(__name__)

# Dictionary to maintain conversation history per sender.
conversation_histories = {}

# --- Helper functions ---

def fetch_products(search_query=None):
    """Fetch products from WooCommerce. If search_query is provided, use it to filter."""
    params = {"per_page": 5}
    if search_query:
        params["search"] = search_query
    response = wcapi.get("products", params=params)
    if response.status_code == 200:
        return response.json()
    else:
        print("WooCommerce API error:", response.text)
        return []

def generate_chat_response(sender, prompt):
    """Generate a conversational response using ChatCompletion API with conversation history."""
    # Initialize conversation history for the sender if not present
    if sender not in conversation_histories:
        conversation_histories[sender] = []
    
    conversation = conversation_histories[sender]
    # Append the new user prompt
    conversation.append({"role": "user", "content": prompt})
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # or "gpt-4" if available
            messages=conversation,
            max_tokens=150,
            temperature=0.7,
        )
        assistant_reply = response["choices"][0]["message"]["content"].strip()
        # Save the assistant's reply in the conversation history
        conversation.append({"role": "assistant", "content": assistant_reply})
        return assistant_reply
    except Exception as e:
        print("Error generating chat response:", e)
        return "Sorry, I couldn't generate a response."

def send_whatsapp_message(recipient_id, message_text):
    """Send a text message via the WhatsApp Cloud API."""
    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": recipient_id,
        "type": "text",
        "text": {"body": message_text}
    }
    response = requests.post(url, headers=headers, json=data)
    if response.ok:
        return response.json()
    else:
        print("WhatsApp API error:", response.text)
        return {}

# --- Webhook endpoint ---
@app.route('/webhook', methods=['GET', 'POST'])
def whatsapp_webhook():
    # Verification request from WhatsApp (GET)
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == VERIFY_TOKEN:
            print("Webhook verified successfully.")
            return challenge, 200
        else:
            return "Verification token mismatch", 403

    # Process incoming message (POST)
    data = request.json
    try:
        entry = data.get('entry', [])[0]
        changes = entry.get('changes', [])[0]
        value = changes.get('value', {})
        messages = value.get('messages', [])
        if messages:
            message = messages[0]
            sender = message.get('from')
            incoming_text = message.get('text', {}).get('body', "").strip().lower()
            print(f"Received message from {sender}: {incoming_text}")

            # If user sends a product search query, use that query to search for products.
            products = fetch_products(search_query=incoming_text)
            if products:
                product_names = [p.get('name') for p in products]
                # Build a prompt that introduces the products
                prompt = f"Introduce these products in a friendly tone: {', '.join(product_names)}."
                chat_response = generate_chat_response(sender, prompt)
                response_message = f"Here are some products matching '{incoming_text}':\n" + "\n".join(product_names) + "\n\n" + chat_response
            else:
                # If no products found, or use the incoming message as a generic conversation
                response_message = generate_chat_response(sender, incoming_text)
            
            send_whatsapp_message(sender, response_message)
    except Exception as e:
        print("Error processing incoming message:", e)
    return "OK", 200

# --- Run Flask app ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)
