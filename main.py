import os
import json
import base64
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, filters, ContextTypes
)
import threading

BOT_TOKEN = os.getenv("8102217053:AAGY8W3EztjicmKcsD87tZynsimEr6jTtPE")
ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Qwer9889")

DATABASE_FILE = "customers.json"
app = Flask(__name__)

bot = Bot(8102217053:AAGY8W3EztjicmKcsD87tZynsimEr6jTtPE)

def load_db():
    if not os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "w") as f:
            json.dump({}, f)
    with open(DATABASE_FILE, "r") as f:
        return json.load(f)

def save_db(db):
    with open(DATABASE_FILE, "w") as f:
        json.dump(db, f, indent=4)

@app.route("/<customer_id>/hik-event", methods=["POST"])
def hik_event(customer_id):
    db = load_db()

    if customer_id not in db:
        return "unknown customer", 404

    chat_id = db[customer_id]["chat_id"]

    data = request.get_json(silent=True)
    if not data:
        return "no json", 400

    event = data.get("AcsEvent") or data
    employee = event.get("name") or event.get("employeeNoString", "Noma'lum")
    time_obj = event.get("time", {})
    event_time = time_obj.get("time") or "Vaqt yo‘q"
    acs_type = event.get("acsEventType", "")

    if acs_type == "entry":
        caption = f"🟢 {employee} ishga keldi\n⏰ {event_time}"
    elif acs_type == "exit":
        caption = f"🔴 {employee} ishdan chiqdi\n⏰ {event_time}"
    else:
        caption = f"{employee}\n⏰ {event_time}"

    pic = event.get("picData")
    if pic:
        img = base64.b64decode(pic)
        bot.send_photo(chat_id=chat_id, photo=img, caption=caption)
    else:
        bot.send_message(chat_id=chat_id, text=caption)

    return "ok"

sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    sessions[uid] = {"step": "login"}
    await update.message.reply_text("🔐 Login kiriting:")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    if uid not in sessions:
        return await update.message.reply_text("Iltimos /start bosing.")

    s = sessions[uid]

    if s["step"] == "login":
        if text == ADMIN_LOGIN:
            s["step"] = "password"
            return await update.message.reply_text("🔑 Parol kiriting:")
        return await update.message.reply_text("❌ Login noto‘g‘ri.")

    if s["step"] == "password":
        if text == ADMIN_PASSWORD:
            s["logged"] = True
            s["step"] = "panel"
            return await update.message.reply_text(
                "✅ Admin panel:\n"
                "/addcustomer\n/list\n/logout"
            )
        return await update.message.reply_text("❌ Parol noto‘g‘ri.")

    if s.get("logged"):
        return await update.message.reply_text(
            "⚙ Buyruqlar:\n/addcustomer\n/list\n/logout"
        )

async def addcustomer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not sessions.get(uid, {}).get("logged"):
        return await update.message.reply_text("❌ Ruxsat yo‘q.")

    db = load_db()
    new_id = f"customer{len(db)+1}"
    db[new_id] = {"chat_id": None}
    save_db(db)

    await update.message.reply_text(
        f"🆕 Mijoz yaratildi: {new_id}\n"
        f"Callback URL:\nhttps://YOUR_RAILWAY_URL/{new_id}/hik-event\n"
        f"Chat ID ni o‘rnatish uchun /setchat ishlatiladi."
    )

async def listcustomers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not sessions.get(uid, {}).get("logged"):
        return await update.message.reply_text("❌ Ruxsat yo‘q.")

    db = load_db()
    text = "📋 Mijozlar:\n\n"
    for cid, data in db.items():
        text += f"🔹 {cid} — chat_id: {data['chat_id']}\n"

    await update.message.reply_text(text)

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sessions.pop(update.effective_user.id, None)
    await update.message.reply_text("🔓 Chiqdingiz.")

def run_bot():
    tg = ApplicationBuilder().token(8102217053:AAGY8W3EztjicmKcsD87tZynsimEr6jTtPEBOT_TOKEN=8102217053:AAGakdqRyEvR_cNNZw92ErHVBvo6QkMJWTU
ADMIN_LOGIN=admin
ADMIN_PASSWORD=Qwer9889BOT_TOKEN=8102217053:AAGakdqRyEvR_cNNZw92ErHVBvo6QkMJWTU
ADMIN_LOGIN=admin
ADMIN_PASSWORD=Qwer9889).build()
    tg.add_handler(CommandHandler("start", start))
    tg.add_handler(CommandHandler("addcustomer", addcustomer))
    tg.add_handler(CommandHandler("list", listcustomers))
    tg.add_handler(CommandHandler("logout", logout))
    tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    tg.run_polling()

threading.Thread(target=run_bot).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
