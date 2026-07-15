"""
ربات پاسخ‌گوی خودکار اینستاگرام - آیتو
این سرور پیام‌های دایرکت و کامنت رو از اینستاگرام می‌گیره،
با شخصیت آیتو (تعریف‌شده تو persona.py) جواب می‌سازه،
و از طریق Instagram Graph API جواب رو ارسال می‌کنه.
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

# --- تنظیمات از متغیرهای محیطی (Environment Variables) ---
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "aito-verify-token")
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")  # توکن صفحه فیسبوک/اینستاگرام
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"  # مدل رایگان و قوی روی Groq
GRAPH_API_VERSION = "v21.0"
GRAPH_API_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"


@app.route("/webhook", methods=["GET"])
def verify_webhook():
    """
    متا (Meta) موقع تنظیم اولیه یه درخواست GET می‌فرسته
    تا مالکیت وبهوک رو تایید کنه.
    """
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("وبهوک با موفقیت تایید شد")
        return challenge, 200

    logger.warning("تایید وبهوک شکست خورد")
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def handle_webhook():
    """
    پیام‌های جدید (دایرکت یا کامنت) از این مسیر دریافت می‌شن.
    """
    data = request.get_json()
    logger.info(f"پیام دریافتی: {json.dumps(data, ensure_ascii=False)}")

    if data.get("object") != "instagram":
        return jsonify({"status": "ignored"}), 200

    for entry in data.get("entry", []):
        for messaging_event in entry.get("messaging", []):
            handle_message_event(messaging_event)

    return jsonify({"status": "ok"}), 200


def handle_message_event(event):
    """پردازش یک پیام دایرکت و ارسال جواب آیتو"""
    sender_id = event.get("sender", {}).get("id")
    message = event.get("message", {})
    text = message.get("text")

    # از پیام‌های اکو (پیام‌هایی که خودمون فرستادیم) صرف‌نظر کن
    if message.get("is_echo") or not text or not sender_id:
        return

    try:
        reply_text = generate_aito_reply(text)
        send_instagram_message(sender_id, reply_text)
    except Exception as e:
        logger.error(f"خطا در پردازش پیام: {e}")


def generate_aito_reply(user_message: str) -> str:
    """
    پیام کاربر رو به Groq API (رایگان) می‌فرسته و جواب رو
    با شخصیت آیتو برمی‌گردونه.
    """
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY تنظیم نشده")

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
    """جواب رو از طریق Instagram Graph API برای کاربر می‌فرسته"""
    params = {"access_token": PAGE_ACCESS_TOKEN}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
    }
    resp = requests.post(GRAPH_API_URL, params=params, json=payload, timeout=15)
    if not resp.ok:
        logger.error(f"ارسال پیام شکست خورد: {resp.text}")
    else:
        logger.info(f"جواب برای {recipient_id} ارسال شد")


@app.route("/", methods=["GET"])
def health_check():
    """برای اطمینان از روشن بودن سرور (مثلاً وقتی Render پینگ می‌کنه)"""
    return jsonify({"status": "آیتو روشنه و منتظر پیامه"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
