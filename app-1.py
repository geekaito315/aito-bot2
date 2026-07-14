"""
Aito Instagram Auto-Reply Bot

This server receives Instagram DMs via webhook, generates a reply
using the Aito persona (defined in persona.py) through the Groq API,
and sends the reply back via the Instagram Graph API.
"""

import os
import json
import logging
import requests
from flask import Flask, request, jsonify

from persona import build_system_prompt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aito-bot")

app = Flask(__name__)

# --- Configuration (from environment variables) ---
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "aito-verify-token")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")  # Facebook Page / Instagram token
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"  # free, strong model on Groq
GRAPH_API_VERSION = "v21.0"
GRAPH_API_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """
    Meta sends a GET request during initial webhook setup
    to verify ownership of the endpoint.
    """
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return challenge, 200

    logger.warning("Webhook verification failed")
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    """
    New messages (DMs or comments) arrive here.
    """
    data = request.get_json()
    logger.info(f"Incoming payload: {json.dumps(data)}")

    if data.get("object") != "instagram":
        return jsonify({"status": "ignored"}), 200

    for entry in data.get("entry", []):
        for messaging_event in entry.get("messaging", []):
            handle_message_event(messaging_event)

    return jsonify({"status": "ok"}), 200


def handle_message_event(event):
    """Process a single DM event and send Aito's reply."""
    sender_id = event.get("sender", {}).get("id")
    message = event.get("message", {})
    text = message.get("text")

    # Skip echo messages (messages the bot itself sent)
    if message.get("is_echo") or not text or not sender_id:
        return

    try:
        reply_text = generate_aito_reply(text)
        send_instagram_message(sender_id, reply_text)
    except Exception as e:
        logger.error(f"Error processing message: {e}")


def generate_aito_reply(user_message: str) -> str:
    """
    Sends the user's message to the Groq API (free tier) and
    returns a reply written in Aito's persona.
    """
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set")

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": GROQ_MODEL,
            "max_tokens": 300,
            "messages": [
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": user_message},
            ],
        },
        timeout=20,
    )
    response.raise_for_status()
    result = response.json()
    return result["choices"][0]["message"]["content"]


def send_instagram_message(recipient_id: str, text: str):
    """Sends the reply to the user via the Instagram Graph API."""
    params = {"access_token": PAGE_ACCESS_TOKEN}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
    }
    resp = requests.post(GRAPH_API_URL, params=params, json=payload, timeout=15)
    if not resp.ok:
        logger.error(f"Failed to send message: {resp.text}")
    else:
        logger.info(f"Reply sent to {recipient_id}")


@app.route("/", methods=["GET"])
def health_check():
    """Simple health check endpoint (e.g. for Render's pings)."""
    return jsonify({"status": "Aito is running and waiting for messages"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
