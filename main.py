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

# ============================
# ENV VARIABLES
# ============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Qwer9889")
BASE_URL = os.getenv("BASE_URL", "https://YOUR-RENDER-URL")

DATABASE_FILE = "customers.json"
app = Flask(__name__)
bot = Bot(BOT_TOKEN)


# ============================
# DATABASE FUNCTIONS
# ============================
def load_db():
    if not os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "w") as f:
            json.dump({}, f)
    with open(DATABASE_FILE, "r") as f:
        return json.load(f)

def save_db(db):
    with open(DATABASE_FILE, "w") as f:
        json.dump(db, f, indent=4)


# ============================
# HIKVISION EVENT HANDLER
# ============================
@app.route("/<customer_id>/hik-event/<device_id>", methods=["POST"])
def hik_event(customer_id, device_id):
    db = load_db()

    if customer_id not in db:
        return "unknown customer", 404

    if device_id not in db[customer_id]["devices"]:
        return "unknown device", 404

    branch_name = db[customer_id]["devices"][device_id]
    chat_id = db[customer_id]["chat_id"]

    data = request.get_json(silent=True)
    if not data:
        return "no json", 400

    event = data.get("AcsEvent") or data
    hik_id = event.get("employeeNoString")
    event_time = event.get("time", {}).get("time", "Vaqt yo‘q")
    acs_type = event.get("acsEventType", "")
    employee = "Noma'lum xodim"

    # Xodimni aniqlash
    if "employees" in db[customer_id] and hik_id in db[customer_id]["employees"]:
        employee = db[customer_id]["employees"][hik_id]["name"]

    # Caption
    if acs_type == "entry":
        caption = f"🏢 {branch_name}\n🟢 {employee} ishga keldi\n⏰ {event_time}"
    elif acs_type == "exit":
        caption = f"🏢 {branch_name}\n🔴 {employee} ishdan chiqdi\n⏰ {event_time}"
    else:
        caption = f"🏢 {branch_name}\n{employee}\n⏰ {event_time}"

    # Rasm bor bo‘lsa yuboramiz
    pic = event.get("picData")
    if pic:
        img = base64.b64decode(pic)
        bot.send_photo(chat_id=chat_id, photo=img, caption=caption)
    else:
        bot.send_message(chat_id=chat_id, text=caption)

    return "ok"


# ============================
# TELEGRAM ADMIN PANEL
# ============================

sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    sessions[uid] = {"step": "login"}
    await update.message.reply_text("🔐 Login kiriting:")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.strip()

    if uid not in sessions:
        return

    s = sessions[uid]

    # LOGIN
    if s["step"] == "login":
        if text == ADMIN_LOGIN:
            s["step"] = "password"
            return await update.message.reply_text("🔑 Parol kiriting:")
        return await update.message.reply_text("❌ Login noto‘g‘ri.")

    # PASSWORD
    if s["step"] == "password":
        if text == ADMIN_PASSWORD:
            s["step"] = "panel"
            s["logged"] = True
            return await update.message.reply_text(
                "✅ Admin panel:\n"
                "/addcustomer\n/adddevice\n/addemployee\n/list\n/logout"
            )
        return await update.message.reply_text("❌ Parol noto‘g‘ri.")

    # ADD EMPLOYEE STEPS
    if s["step"] == "emp_name":
        s["temp"]["name"] = text
        s["step"] = "emp_position"
        return await update.message.reply_text("💼 Lavozimini kiriting:")

    if s["step"] == "emp_position":
        s["temp"]["position"] = text
        s["step"] = "emp_hikid"
        return await update.message.reply_text("🔢 Hikvision ID kiriting:")

    if s["step"] == "emp_hikid":
        s["temp"]["hik_id"] = text
        s["step"] = "emp_photo"
        return await update.message.reply_text("📸 Xodimning rasmini yuboring:")

    # Logged commands
    if s.get("logged"):
        return await update.message.reply_text(
            "⚙ Buyruqlar:\n/addcustomer\n/adddevice\n/addemployee\n/list\n/logout"
        )


# ============================
# ADD CUSTOMER
# ============================
async def addcustomer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not sessions.get(uid, {}).get("logged"):
        return await update.message.reply_text("❌ Ruxsat yo‘q.")

    db = load_db()
    new_id = f"customer{len(db)+1}"

    db[new_id] = {
        "chat_id": uid,
        "devices": {},
        "employees": {}
    }

    save_db(db)
    await update.message.reply_text(
        f"🆕 Mijoz yaratildi: {new_id}\n"
        f"Filial qo‘shish uchun /adddevice"
    )


# ============================
# ADD BRANCH (DEVICE)
# ============================
async def adddevice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not sessions.get(uid, {}).get("logged"):
        return await update.message.reply_text("❌ Ruxsat yo‘q.")

    db = load_db()
    customer_id = list(db.keys())[-1]

    device_num = len(db[customer_id]["devices"]) + 1
    device_id = f"device{device_num}"
    db[customer_id]["devices"][device_id] = f"Filial {device_num}"

    save_db(db)
    url = f"{BASE_URL}/{customer_id}/hik-event/{device_id}"

    await update.message.reply_text(
        f"🏢 Filial qo‘shildi!\n"
        f"Device ID: {device_id}\n"
        f"Webhook URL:\n{url}"
    )


# ============================
# ADD EMPLOYEE (PHOTO)
# ============================
async def addemployee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not sessions.get(uid, {}).get("logged"):
        return await update.message.reply_text("❌ Ruxsat yo‘q.")

    sessions[uid] = {"step": "emp_name", "temp": {}}
    await update.message.reply_text("👤 Xodim ismini kiriting:")


# PHOTO HANDLER
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in sessions:
        return

    s = sessions[uid]
    if s["step"] != "emp_photo":
        return

    photo = update.message.photo[-1]
    file_id = photo.file_id
    file = await context.bot.get_file(file_id)

    if not os.path.exists("employees_photos"):
        os.makedirs("employees_photos")

    path = f"employees_photos/{s['temp']['hik_id']}.jpg"
    await file.download_to_drive(path)

    db = load_db()
    customer_id = list(db.keys())[-1]

    db[customer_id]["employees"][s["temp"]["hik_id"]] = {
        "name": s["temp"]["name"],
        "position": s["temp"]["position"],
        "photo": path
    }

    save_db(db)

    await update.message.reply_text(
        "✅ Xodim qo‘shildi!\n"
        f"👤 {s['temp']['name']}\n"
        f"💼 {s['temp']['position']}\n"
        f"🆔 {s['temp']['hik_id']}\n"
        "📸 Rasm saqlandi!"
    )

    sessions.pop(uid)


# ============================
# RUN TELEGRAM BOT
# ============================
def run_bot():
    tg = ApplicationBuilder().token(BOT_TOKEN).build()
    tg.add_handler(CommandHandler("start", start))
    tg.add_handler(CommandHandler("addcustomer", addcustomer))
    tg.add_handler(CommandHandler("adddevice", adddevice))
    tg.add_handler(CommandHandler("addemployee", addemployee))
    tg.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    tg.run_polling()

threading.Thread(target=run_bot).start()


# ============================
# RUN FLASK SERVER
# ============================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
