import os
import json
import base64
import threading
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, CallbackContext
)

# ========= CONFIG =========
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Qwer9889")
BASE_URL = os.getenv("BASE_URL", "https://YOUR-RENDER-URL")

DATABASE_FILE = "customers.json"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env variable is not set")

app = Flask(__name__)
updater: Updater = None  # main() ichida to'ldiriladi


# ========= DB HELPERS =========
def load_db():
    if not os.path.exists(DATABASE_FILE):
        with open(DATABASE_FILE, "w") as f:
            json.dump({}, f)
    with open(DATABASE_FILE, "r") as f:
        return json.load(f)


def save_db(db):
    with open(DATABASE_FILE, "w") as f:
        json.dump(db, f, indent=4)


# ========= FLASK: HIKVISION EVENT =========
@app.route("/<company_id>/<device_id>/event", methods=["POST"])
def hik_event(company_id, device_id):
    db = load_db()

    if company_id not in db:
        return "unknown company", 404

    company = db[company_id]
    devices = company.get("devices", {})
    if device_id not in devices:
        return "unknown device", 404

    chat_id = company.get("chat_id")
    branch_name = devices[device_id]

    data = request.get_json(silent=True)
    if not data:
        return "no json", 400

    event = data.get("AcsEvent") or data

    hik_id = event.get("employeeNoString")
    time_obj = event.get("time", {})
    event_time = time_obj.get("time") or "Vaqt ko‘rsatilmagan"
    acs_type = event.get("acsEventType", "")

    employees = company.get("employees", {})
    employee_name = "Noma'lum xodim"
    if hik_id and hik_id in employees:
        employee_name = employees[hik_id].get("name", employee_name)

    if acs_type == "entry":
        caption = f"🏢 {branch_name}\n🟢 {employee_name} ishga keldi\n⏰ {event_time}"
    elif acs_type == "exit":
        caption = f"🏢 {branch_name}\n🔴 {employee_name} ishdan chiqdi\n⏰ {event_time}"
    else:
        caption = f"🏢 {branch_name}\n{employee_name}\n⏰ {event_time}"

    bot: Bot = updater.bot

    pic = event.get("picData")
    try:
        if pic:
            img_bytes = base64.b64decode(pic)
            bot.send_photo(chat_id=chat_id, photo=img_bytes, caption=caption)
        else:
            bot.send_message(chat_id=chat_id, text=caption)
    except Exception as e:
        print("Telegram send error:", e)

    return "ok"


# ========= TELEGRAM ADMIN PANEL =========
sessions = {}


def require_admin(func):
    def wrapper(update: Update, context: CallbackContext):
        uid = update.effective_user.id
        s = sessions.get(uid)
        if not s or not s.get("is_admin"):
            update.message.reply_text("❌ Ruxsat yo‘q. /start orqali admin sifatida kiring.")
            return
        return func(update, context)
    return wrapper


def start(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    sessions[uid] = {"state": "login", "is_admin": False, "temp": {}}
    update.message.reply_text("🔐 Admin panelga kirish uchun loginni kiriting:")


def handle_text(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    text = (update.message.text or "").strip()

    if uid not in sessions:
        update.message.reply_text("Iltimos /start buyrug‘ini bosing.")
        return

    s = sessions[uid]
    state = s.get("state")

    # === LOGIN ===
    if state == "login":
        if text == ADMIN_LOGIN:
            s["state"] = "password"
            update.message.reply_text("🔑 Parolni kiriting:")
        else:
            update.message.reply_text("❌ Login noto‘g‘ri. Qayta kiriting.")
        return

    # === PASSWORD ===
    if state == "password":
        if text == ADMIN_PASSWORD:
            s["state"] = "idle"
            s["is_admin"] = True
            s["current_company"] = None
            update.message.reply_text(
                "✅ Admin panelga xush kelibsiz!\n\n"
                "Buyruqlar:\n"
                "/addcompany - yangi mijoz\n"
                "/usecompany - mavjud mijozni tanlash\n"
                "/adddevice - filial (qurilma) qo‘shish\n"
                "/addemployee - xodim qo‘shish\n"
                "/list - mijozlar ro‘yxati\n"
                "/logout - chiqish"
            )
        else:
            update.message.reply_text("❌ Parol noto‘g‘ri. Qayta kiriting.")
        return

    # === EMPLOYEE ADDING FLOW ===
    if state == "emp_name":
        s["temp"]["name"] = text
        s["state"] = "emp_position"
        update.message.reply_text("💼 Xodim lavozimini kiriting:")
        return

    if state == "emp_position":
        s["temp"]["position"] = text
        s["state"] = "emp_hikid"
        update.message.reply_text("🔢 Hikvision ID (employeeNo) ni kiriting:")
        return

    if state == "emp_hikid":
        s["temp"]["hik_id"] = text
        s["state"] = "emp_photo"
        update.message.reply_text("📸 Endi xodimning rasmini yuboring:")
        return

    # Admin default
    if s.get("is_admin"):
        update.message.reply_text(
            "⚙ Buyruqlar:\n"
            "/addcompany\n/usecompany\n/adddevice\n/addemployee\n/list\n/logout"
        )


@require_admin
def addcompany(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    db = load_db()

    new_id = f"company{len(db) + 1}"
    db[new_id] = {
        "chat_id": uid,
        "devices": {},
        "employees": {}
    }
    save_db(db)

    sessions[uid]["current_company"] = new_id

    update.message.reply_text(
        f"🆕 Yangi mijoz yaratildi: {new_id}\n"
        f"Endi /adddevice orqali qurilma qo‘shing."
    )


@require_admin
def usecompany(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    args = context.args

    if not args:
        update.message.reply_text("Qanday ishlatish: /usecompany company1")
        return

    company_id = args[0]
    db = load_db()

    if company_id not in db:
        update.message.reply_text("❌ Bunday mijoz topilmadi.")
        return

    sessions[uid]["current_company"] = company_id
    update.message.reply_text(f"✅ Tanlangan mijoz: {company_id}")


@require_admin
def adddevice(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    s = sessions[uid]
    current_company = s.get("current_company")

    if not current_company:
        update.message.reply_text("Avval /addcompany yoki /usecompany bilan mijoz tanlang.")
        return

    db = load_db()
    company = db[current_company]

    devices = company.get("devices", {})
    device_num = len(devices) + 1
    device_id = f"device{device_num}"
    branch_name = f"Filial {device_num}"

    devices[device_id] = branch_name
    company["devices"] = devices
    db[current_company] = company
    save_db(db)

    url = f"{BASE_URL}/{current_company}/{device_id}/event"

    update.message.reply_text(
        f"🏢 Filial qo‘shildi!\n"
        f"Device ID: {device_id}\n"
        f"Filial: {branch_name}\n\n"
        f"➡ Hikvision URL:\n{url}"
    )


@require_admin
def addemployee(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    s = sessions[uid]
    if not s.get("current_company"):
        update.message.reply_text("Avval /usecompany bilan mijoz tanlang.")
        return

    s["state"] = "emp_name"
    s["temp"] = {}
    update.message.reply_text("👤 Xodim to‘liq ismini kiriting:")


def photo_handler(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    if uid not in sessions:
        return

    s = sessions[uid]
    if s.get("state") != "emp_photo":
        return

    current_company = s.get("current_company")
    if not current_company:
        update.message.reply_text("Mijoz tanlanmagan.")
        return

    photo_list = update.message.photo
    if not photo_list:
        update.message.reply_text("📸 Iltimos rasm yuboring.")
        return

    largest = photo_list[-1]
    file_id = largest.file_id
    file = context.bot.get_file(file_id)

    if not os.path.exists("employees_photos"):
        os.makedirs("employees_photos")

    hik_id = s["temp"]["hik_id"]
    path = os.path.join("employees_photos", f"{hik_id}.jpg")
    file.download(path)

    db = load_db()
    company = db[current_company]
    employees = company.get("employees", {})

    employees[hik_id] = {
        "name": s["temp"]["name"],
        "position": s["temp"]["position"],
        "photo": path
    }
    company["employees"] = employees
    db[current_company] = company
    save_db(db)

    update.message.reply_text(
        "✅ Xodim qo‘shildi!\n"
        f"👤 {s['temp']['name']}\n"
        f"💼 {s['temp']['position']}\n"
        f"🆔 {hik_id}\n"
        f"📸 Rasm saqlandi!"
    )

    s["state"] = "idle"
    s["temp"] = {}


@require_admin
def list_companies(update: Update, context: CallbackContext):
    db = load_db()
    if not db:
        update.message.reply_text("Mijozlar hali yo‘q.")
        return

    lines = ["📋 Mijozlar ro‘yxati:\n"]
    for cid, data in db.items():
        dev_count = len(data.get("devices", {}))
        emp_count = len(data.get("employees", {}))
        lines.append(f"🔹 {cid} — filial: {dev_count}, xodim: {emp_count}")
    update.message.reply_text("\n".join(lines))


def logout(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    sessions.pop(uid, None)
    update.message.reply_text("🔓 Sessiya tugadi. /start orqali qayta kirishingiz mumkin.")


# ========= RUNNERS =========
def run_flask():
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)


def main():
    global updater
    updater = Updater(BOT_TOKEN, use_context=True)

    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("addcompany", addcompany))
    dp.add_handler(CommandHandler("usecompany", usecompany, pass_args=True))
    dp.add_handler(CommandHandler("adddevice", adddevice))
    dp.add_handler(CommandHandler("addemployee", addemployee))
    dp.add_handler(CommandHandler("list", list_companies))
    dp.add_handler(CommandHandler("logout", logout))

    dp.add_handler(MessageHandler(Filters.photo, photo_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

    threading.Thread(target=run_flask, daemon=True).start()

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
