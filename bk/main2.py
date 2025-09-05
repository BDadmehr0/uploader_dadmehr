import asyncio
import logging
import pickle
import sqlite3
import uuid

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      KeyboardButton, ReplyKeyboardMarkup, Update)
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

# تنظیمات لاگ
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

BOT_TOKEN = "8339151235:AAHWAVBU0E0BFS9OGncjYXQwdU8XqHY83aQ"

ADMIN_IDS = [2120880112]

DEFAULT_SELF_DESTRUCT_TIME = 30


def init_db():
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id TEXT NOT NULL,
        file_name TEXT NOT NULL,
        file_type TEXT NOT NULL,
        caption TEXT,
        caption_entities BLOB,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        unique_code TEXT UNIQUE NOT NULL,
        archive_id INTEGER DEFAULT NULL,
        self_destruct INTEGER DEFAULT 0,
        destroy_time INTEGER DEFAULT NULL
    )
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS archives (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        archive_name TEXT NOT NULL,
        archive_code TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        self_destruct INTEGER DEFAULT 0
    )
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        entity_id INTEGER NOT NULL,
        self_destruct_time INTEGER DEFAULT 30,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    )

    conn.commit()
    conn.close()


# بررسی آیا کاربر ادمین است
def is_admin(user_id):
    return user_id in ADMIN_IDS


# پنل مدیریت ادمین
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    # پاک کردن وضعیت‌های قبلی
    context.user_data.clear()

    keyboard = [
        [KeyboardButton("📤 آپلود فایل جدید"), KeyboardButton("📦 آرشیو پست")],
        [KeyboardButton("📋 لیست فایل‌ها"), KeyboardButton("🗑 حذف فایل")],
        [KeyboardButton("⚙️ تنظیمات"), KeyboardButton("👥 مدیریت ادمین‌ها")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "پنل مدیریت - گزینه مورد نظر را انتخاب کنید:", reply_markup=reply_markup
    )


# منوی تنظیمات
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    keyboard = [
        [InlineKeyboardButton("⚙️ تنظیمات فایل", callback_data="settings_file")],
        [InlineKeyboardButton("⚙️ تنظیمات آرشیو", callback_data="settings_archive")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "تنظیمات - لطفاً گزینه مورد نظر را انتخاب کنید:", reply_markup=reply_markup
    )


# پردازش انتخاب تنظیمات
async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    data = query.data

    if data == "settings_file":
        await show_file_settings(query)
    elif data == "settings_archive":
        await show_archive_settings(query)
    elif data == "back_to_main":
        await admin_panel_from_query(query, context)
    elif data.startswith("file_"):
        await handle_file_settings(query, data)
    elif data.startswith("archive_"):
        await handle_archive_settings(query, data)
    elif data.startswith("set_time_"):
        await handle_set_time(query, data, context)

    # 🔹 فعال/غیرفعال کردن تخریب خودکار فایل‌ها
    elif data.startswith("enable_file_"):
        file_id = int(data[12:])
        await enable_self_destruct_file(query, file_id)

    elif data.startswith("disable_file_"):
        file_id = int(data[13:])
        await disable_self_destruct_file(query, file_id)

    # 🔹 فعال/غیرفعال کردن تخریب خودکار آرشیوها
    elif data.startswith("enable_archive_"):
        archive_id = int(data[15:])
        await enable_self_destruct_archive(query, archive_id)

    elif data.startswith("disable_archive_"):
        archive_id = int(data[16:])
        await disable_self_destruct_archive(query, archive_id)


# نمایش تنظیمات فایل‌ها
async def show_file_settings(query):
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, file_name, self_destruct FROM files ORDER BY id DESC LIMIT 10"
    )
    files = cursor.fetchall()
    conn.close()

    keyboard = []
    for file in files:
        file_id, file_name, self_destruct = file
        status = "✅" if self_destruct else "❌"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{status} {file_name}", callback_data=f"file_{file_id}"
                )
            ]
        )

    keyboard.append(
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_settings")]
    )
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.edit_text(
        "فایل‌ها - انتخاب فایل برای تنظیم تخریب خودکار:", reply_markup=reply_markup
    )


# نمایش تنظیمات آرشیوها
async def show_archive_settings(query):
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, archive_name, self_destruct FROM archives ORDER BY id DESC"
    )
    archives = cursor.fetchall()
    conn.close()

    keyboard = []
    for archive in archives:
        archive_id, archive_name, self_destruct = archive
        status = "✅" if self_destruct else "❌"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{status} {archive_name}", callback_data=f"archive_{archive_id}"
                )
            ]
        )

    keyboard.append(
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_settings")]
    )
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.edit_text(
        "آرشیوها - انتخاب آرشیو برای تنظیم تخریب خودکار:", reply_markup=reply_markup
    )


# پردازش تنظیمات فایل
async def handle_file_settings(query, data):
    file_id = int(data[5:])

    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT file_name, self_destruct FROM files WHERE id = ?", (file_id,)
    )
    file_data = cursor.fetchone()
    conn.close()

    if not file_data:
        await query.message.reply_text("فایل مورد نظر یافت نشد.")
        return

    file_name, self_destruct = file_data
    status = "فعال" if self_destruct else "غیرفعال"

    keyboard = [
        [
            InlineKeyboardButton(
                "✅ فعال کردن تخریب خودکار", callback_data=f"enable_file_{file_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ غیرفعال کردن تخریب خودکار", callback_data=f"disable_file_{file_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "⏰ تنظیم زمان تخریب", callback_data=f"set_time_file_{file_id}"
            )
        ],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="settings_file")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.edit_text(
        f"تنظیمات فایل: {file_name}\n\n"
        f"تخریب خودکار: {status}\n"
        f"زمان پیش‌فرض: {DEFAULT_SELF_DESTRUCT_TIME} ثانیه",
        reply_markup=reply_markup,
    )


# پردازش تنظیمات آرشیو
async def handle_archive_settings(query, data):
    archive_id = int(data[8:])

    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT archive_name, self_destruct FROM archives WHERE id = ?", (archive_id,)
    )
    archive_data = cursor.fetchone()
    conn.close()

    if not archive_data:
        await query.message.reply_text("آرشیو مورد نظر یافت نشد.")
        return

    archive_name, self_destruct = archive_data
    status = "فعال" if self_destruct else "غیرفعال"

    keyboard = [
        [
            InlineKeyboardButton(
                "✅ فعال کردن تخریب خودکار",
                callback_data=f"enable_archive_{archive_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "❌ غیرفعال کردن تخریب خودکار",
                callback_data=f"disable_archive_{archive_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "⏰ تنظیم زمان تخریب", callback_data=f"set_time_archive_{archive_id}"
            )
        ],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="settings_archive")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.edit_text(
        f"تنظیمات آرشیو: {archive_name}\n\n"
        f"تخریب خودکار: {status}\n"
        f"زمان پیش‌فرض: {DEFAULT_SELF_DESTRUCT_TIME} ثانیه",
        reply_markup=reply_markup,
    )


# فعال کردن تخریب خودکار برای فایل
async def enable_self_destruct_file(query, file_id):
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE files SET self_destruct = 1 WHERE id = ?", (file_id,))
    conn.commit()
    conn.close()

    await query.answer("تخریب خودکار فعال شد!")
    await handle_file_settings(query, f"file_{file_id}")


# غیرفعال کردن تخریب خودکار برای فایل
async def disable_self_destruct_file(query, file_id):
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE files SET self_destruct = 0 WHERE id = ?", (file_id,))
    conn.commit()
    conn.close()

    await query.answer("تخریب خودکار غیرفعال شد!")
    await handle_file_settings(query, f"file_{file_id}")


# فعال کردن تخریب خودکار برای آرشیو
async def enable_self_destruct_archive(query, archive_id):
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE archives SET self_destruct = 1 WHERE id = ?", (archive_id,))
    conn.commit()
    conn.close()

    await query.answer("تخریب خودکار فعال شد!")
    await handle_archive_settings(query, f"archive_{archive_id}")


# غیرفعال کردن تخریب خودکار برای آرشیو
async def disable_self_destruct_archive(query, archive_id):
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE archives SET self_destruct = 0 WHERE id = ?", (archive_id,))
    conn.commit()
    conn.close()

    await query.answer("تخریب خودکار غیرفعال شد!")
    await handle_archive_settings(query, f"archive_{archive_id}")


# تنظیم زمان تخریب
async def handle_set_time(query, data, context):
    parts = data.split("_")
    entity_type = parts[2]  # file یا archive
    entity_id = int(parts[3])

    context.user_data["setting_time_for"] = {"type": entity_type, "id": entity_id}
    context.user_data["waiting_for_time"] = True

    await query.message.edit_text(
        "لطفاً زمان تخریب خودکار را به ثانیه وارد کنید:\n\n" "مثال: 30 (برای ۳۰ ثانیه)"
    )


# پردازش زمان وارد شده
async def handle_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    if "waiting_for_time" not in context.user_data:
        return

    try:
        time_seconds = int(update.message.text.strip())
        if time_seconds < 5:
            await update.message.reply_text("زمان باید حداقل ۵ ثانیه باشد.")
            return

        entity_info = context.user_data["setting_time_for"]
        entity_type = entity_info["type"]
        entity_id = entity_info["id"]

        conn = sqlite3.connect("file_bot.db")
        cursor = conn.cursor()

        # حذف تنظیمات قبلی
        cursor.execute(
            "DELETE FROM settings WHERE entity_type = ? AND entity_id = ?",
            (entity_type, entity_id),
        )

        # افزودن تنظیمات جدید
        cursor.execute(
            "INSERT INTO settings (entity_type, entity_id, self_destruct_time) VALUES (?, ?, ?)",
            (entity_type, entity_id, time_seconds),
        )

        conn.commit()
        conn.close()

        del context.user_data["waiting_for_time"]
        del context.user_data["setting_time_for"]

        await update.message.reply_text(
            f"زمان تخریب خودکار به {time_seconds} ثانیه تنظیم شد."
        )

    except ValueError:
        await update.message.reply_text("لطفاً یک عدد معتبر وارد کنید.")


# تابع تخریب خودکار پیام‌ها
async def self_destruct_messages(chat_id, message_ids, context, delay_seconds):
    await asyncio.sleep(delay_seconds)

    try:
        for msg_id in message_ids:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception as e:
                logging.error(f"Error deleting message {msg_id}: {e}")
    except Exception as e:
        logging.error(f"Error in self_destruct: {e}")


# دریافت زمان تخریب برای یک موجودیت
def get_self_destruct_time(entity_type, entity_id):
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT self_destruct_time FROM settings WHERE entity_type = ? AND entity_id = ?",
        (entity_type, entity_id),
    )
    result = cursor.fetchone()
    conn.close()

    return result[0] if result else DEFAULT_SELF_DESTRUCT_TIME


# بررسی آیا تخریب خودکار فعال است
def is_self_destruct_enabled(entity_type, entity_id):
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()

    if entity_type == "file":
        cursor.execute("SELECT self_destruct FROM files WHERE id = ?", (entity_id,))
    else:  # archive
        cursor.execute("SELECT self_destruct FROM archives WHERE id = ?", (entity_id,))

    result = cursor.fetchone()
    conn.close()

    return result[0] if result else 0


# ارسال فایل تکی با قابلیت تخریب خودکار
async def send_single_file(
    update: Update, context: ContextTypes.DEFAULT_TYPE, file_data
):
    file_db_id = file_data[0]
    file_id = file_data[1]
    file_type = file_data[3]
    caption = file_data[4] or ""

    # بازیابی caption_entities از دیتابیس
    caption_entities = None
    if file_data[5] and isinstance(file_data[5], (bytes, bytearray)):
        try:
            caption_entities = pickle.loads(file_data[5])
        except Exception as e:
            logging.error(f"Error loading caption entities: {e}")
            caption_entities = None

    message = None  # مقداردهی اولیه برای جلوگیری از خطا
    try:
        if file_type == "document":
            message = await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=file_id,
                caption=caption,
                caption_entities=caption_entities,
            )
        elif file_type == "video":
            message = await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=file_id,
                caption=caption,
                caption_entities=caption_entities,
                has_spoiler=True,
            )
        elif file_type == "audio":
            message = await context.bot.send_audio(
                chat_id=update.effective_chat.id,
                audio=file_id,
                caption=caption,
                caption_entities=caption_entities,
            )
        elif file_type == "photo":
            message = await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=file_id,
                caption=caption,
                caption_entities=caption_entities,
                has_spoiler=True,
            )

        # بررسی و اعمال تخریب خودکار
        if message and is_self_destruct_enabled("file", file_db_id):
            destruct_time = get_self_destruct_time("file", file_db_id)
            asyncio.create_task(
                self_destruct_messages(
                    update.effective_chat.id,
                    [message.message_id],
                    context,
                    destruct_time,
                )
            )

    except Exception as e:
        logging.error(f"Error sending file: {e}")
        await update.message.reply_text("⚠️ خطا در ارسال فایل.")


# ارسال فایل‌های یک آرشیو با قابلیت تخریب خودکار
async def send_archive_files(
    update: Update, context: ContextTypes.DEFAULT_TYPE, archive_code
):
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, archive_name FROM archives WHERE archive_code = ?", (archive_code,)
    )
    archive_data = cursor.fetchone()

    if not archive_data:
        await update.message.reply_text("آرشیو مورد نظر یافت نشد.")
        return

    archive_id, archive_name = archive_data

    cursor.execute(
        "SELECT * FROM files WHERE archive_id = ? ORDER BY id", (archive_id,)
    )
    files_data = cursor.fetchall()

    conn.close()

    if not files_data:
        await update.message.reply_text("هیچ فایلی در این آرشیو یافت نشد.")
        return

    welcome_msg = await update.message.reply_text(f"📦 آرشیو: {archive_name}")
    message_ids = [welcome_msg.message_id]

    for file_data in files_data:
        file_id = file_data[1]
        file_type = file_data[3]
        caption = file_data[4] or ""

        # بازیابی caption_entities از دیتابیس
        caption_entities = None
        if file_data[5]:
            try:
                caption_entities = pickle.loads(file_data[5])
            except Exception as e:
                logging.error(f"Error loading caption entities: {e}")

        try:
            if file_type == "document":
                msg = await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=file_id,
                    caption=caption,
                    caption_entities=caption_entities,
                )
            elif file_type == "video":
                msg = await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=file_id,
                    caption=caption,
                    caption_entities=caption_entities,
                    has_spoiler=True,
                )
            elif file_type == "audio":
                msg = await context.bot.send_audio(
                    chat_id=update.effective_chat.id,
                    audio=file_id,
                    caption=caption,
                    caption_entities=caption_entities,
                )
            elif file_type == "photo":
                msg = await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=file_id,
                    caption=caption,
                    caption_entities=caption_entities,
                    has_spoiler=True,
                )

            message_ids.append(msg.message_id)

        except Exception as e:
            logging.error(f"Error sending file: {e}")
            await update.message.reply_text("خطا در ارسال فایل.")

    # بررسی و اعمال تخریب خودکار برای آرشیو
    if is_self_destruct_enabled("archive", archive_id):
        destruct_time = get_self_destruct_time("archive", archive_id)
        asyncio.create_task(
            self_destruct_messages(
                update.effective_chat.id, message_ids, context, destruct_time
            )
        )


# بازگشت به پنل اصلی از طریق query
async def admin_panel_from_query(query, context):
    await query.message.delete()
    await admin_panel(
        Update(message=query.message, effective_user=query.from_user), context
    )


# بازگشت به منوی تنظیمات
async def back_to_settings(query):
    await settings_menu(
        Update(message=query.message, effective_user=query.from_user), None
    )


async def start_create_archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    # پاک کردن وضعیت‌های قبلی
    if "waiting_for_file" in context.user_data:
        del context.user_data["waiting_for_file"]

    # دریافت لیست آرشیوهای موجود
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, archive_name, archive_code FROM archives ORDER BY id DESC"
    )
    archives = cursor.fetchall()
    conn.close()

    keyboard = [
        [InlineKeyboardButton("➕ ایجاد آرشیو جدید", callback_data="new_archive")],
    ]

    for archive in archives:
        archive_id, archive_name, archive_code = archive
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"📁 {archive_name}", callback_data=f"open_arc_{archive_code}"
                )
            ]
        )

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "آرشیوهای موجود:\n\n"
        "برای ایجاد آرشیو جدید روی دکمه زیر کلیک کنید یا یک آرشیو موجود را انتخاب کنید:",
        reply_markup=reply_markup,
    )


# هندلر برای دکمه تنظیمات
async def handle_settings_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await settings_menu(update, context)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if args and args[0].startswith("get_"):
        unique_code = args[0][4:]

        conn = sqlite3.connect("file_bot.db")
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, file_id, file_name, file_type, caption, caption_entities, self_destruct
            FROM files WHERE unique_code = ?
        """,
            (unique_code,),
        )
        file_data = cursor.fetchone()
        conn.close()

        if file_data:
            (
                file_db_id,
                file_id,
                file_name,
                file_type,
                caption,
                caption_entities,
                self_destruct,
            ) = file_data

            # 📂 ابتدا فایل ارسال شود
            await send_single_file(update, context, file_data)

            # ⚠️ سپس هشدار تخریب خودکار
            if self_destruct:
                warning_msg = (
                    f"⚠️ این فایل دارای تخریب خودکار است!\n\n"
                    "📌 لطفاً بلافاصله فایل را به Saved Messages خود منتقل کنید تا از دست نرود."
                )
                await update.message.reply_text(warning_msg)

        else:
            await update.message.reply_text("فایل مورد نظر یافت نشد.")

    elif args and args[0].startswith("arc_"):
        archive_code = args[0][4:]
        await send_archive_files(update, context, archive_code)
    else:
        if is_admin(user_id):
            await admin_panel(update, context)
        else:
            await update.message.reply_text(
                "سلام! به ربات ما خوش آمدید.\n\n"
                "برای دریافت فایل از لینک اختصاصی آن استفاده کنید."
            )


async def handle_archive_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    data = query.data

    if data == "new_archive":
        # قرار دادن وضعیت برای ایجاد آرشیو جدید
        context.user_data["waiting_for_archive_name"] = True
        await query.message.reply_text("لطفاً یک نام برای آرشیو جدید وارد کنید:")
        return

    if data.startswith("open_arc_"):
        archive_code = data[9:]

        # ذخیره آرشیو انتخاب شده در context
        context.user_data["current_archive"] = archive_code

        # دریافت اطلاعات آرشیو
        conn = sqlite3.connect("file_bot.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT archive_name FROM archives WHERE archive_code = ?", (archive_code,)
        )
        archive_data = cursor.fetchone()
        conn.close()

        if archive_data:
            archive_name = archive_data[0]
            await query.message.reply_text(
                f"شما در حال حاضر در آرشیو '{archive_name}' هستید.\n\n"
                f"لطفاً فایل‌های مورد نظر را برای این آرشیو ارسال کنید."
            )
        else:
            await query.message.reply_text("آرشیو مورد نظر یافت نشد.")


# مدیریت فایل‌های ارسالی توسط ادمین
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    # بررسی وضعیت آپلود: یا فایل جدید یا افزودن به آرشیو
    is_waiting = "waiting_for_file" in context.user_data
    is_archive = "current_archive" in context.user_data

    if not is_waiting and not is_archive:
        await update.message.reply_text(
            "لطفاً ابتدا از منو گزینه '📤 آپلود فایل جدید' را انتخاب کنید."
        )
        return

    message = update.message

    # شناسایی نوع فایل
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name
        file_type = "document"
    elif message.video:
        file_id = message.video.file_id
        file_name = message.video.file_name or "video.mp4"
        file_type = "video"
    elif message.audio:
        file_id = message.audio.file_id
        file_name = message.audio.file_name or "audio.mp3"
        file_type = "audio"
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_name = "photo.jpg"
        file_type = "photo"
    else:
        await message.reply_text("فرمت فایل پشتیبانی نمی‌شود.")
        return

    caption = message.caption or ""
    caption_entities = message.caption_entities or []
    unique_code = str(uuid.uuid4()).replace("-", "")[:12]

    # تبدیل caption_entities به بایت برای ذخیره در دیتابیس
    entities_blob = pickle.dumps(caption_entities) if caption_entities else None

    archive_id = None
    archive_code = None

    if is_archive:
        archive_code = context.user_data["current_archive"]
        conn = sqlite3.connect("file_bot.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM archives WHERE archive_code = ?", (archive_code,)
        )
        archive_data = cursor.fetchone()
        if archive_data:
            archive_id = archive_data[0]
        conn.close()

    # ذخیره فایل در دیتابیس
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO files (file_id, file_name, file_type, caption, caption_entities, unique_code, archive_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            file_id,
            file_name,
            file_type,
            caption,
            entities_blob,
            unique_code,
            archive_id,
        ),
    )
    conn.commit()
    conn.close()

    # حذف وضعیت waiting_for_file فقط اگر فایل جدید بود
    if is_waiting:
        del context.user_data["waiting_for_file"]

    bot_username = context.bot.username

    # ارسال لینک
    if archive_id:
        file_link = f"https://t.me/{bot_username}?start=arc_{archive_code}"
        await message.reply_text(
            f"فایل با موفقیت به آرشیو اضافه شد!\n\nلینک آرشیو:\n`{file_link}`",
            parse_mode="Markdown",
        )
    else:
        file_link = f"https://t.me/{bot_username}?start=get_{unique_code}"
        await message.reply_text(
            f"فایل با موفقیت ذخیره شد!\n\nلینک اختصاصی:\n`{file_link}`",
            parse_mode="Markdown",
        )


# هندلر برای دکمه "آپلود فایل جدید"
async def start_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    # قرار دادن وضعیت برای انتظار دریافت فایل
    context.user_data["waiting_for_file"] = True

    # پاک کردن وضعیت ایجاد آرشیو اگر وجود دارد
    if "waiting_for_archive_name" in context.user_data:
        del context.user_data["waiting_for_archive_name"]

    await update.message.reply_text("لطفاً فایل خود را ارسال کنید.")


# نمایش لیست فایل‌ها
async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT f.id, f.file_name, f.file_type, f.created_at, f.unique_code, a.archive_name
        FROM files f
        LEFT JOIN archives a ON f.archive_id = a.id
        ORDER BY f.id DESC
    """
    )
    files = cursor.fetchall()
    conn.close()

    if not files:
        await update.message.reply_text("هیچ فایلی وجود ندارد.")
        return

    bot_username = context.bot.username
    message = "📋 لیست فایل‌ها:\n\n"

    for file in files:
        file_id, file_name, file_type, created_at, unique_code, archive_name = file
        file_link = f"https://t.me/{bot_username}?start=get_{unique_code}"

        if archive_name:
            message += f"📁 {file_name} (در آرشیو: {archive_name})\n🔗 {file_link}\n📅 {created_at}\n\n"
        else:
            message += f"📁 {file_name}\n🔗 {file_link}\n📅 {created_at}\n\n"

    await update.message.reply_text(message)


async def delete_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    await update.message.reply_text("این قابلیت به زودی اضافه خواهد شد.")


async def manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    admin_list = "\n".join([f"🆔 {admin_id}" for admin_id in ADMIN_IDS])
    await update.message.reply_text(f"لیست ادمین‌ها:\n{admin_list}")


async def handle_archive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    archive_name = update.message.text.strip()
    archive_code = str(uuid.uuid4()).replace("-", "")[:12]

    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO archives (archive_name, archive_code) VALUES (?, ?)",
        (archive_name, archive_code),
    )
    conn.commit()
    conn.close()

    del context.user_data["waiting_for_archive_name"]
    await update.message.reply_text(
        f"آرشیو '{archive_name}' ایجاد شد!\nکد: {archive_code}"
    )


# هندلر برای متون معمولی
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    # اگر کاربر در حال ایجاد آرشیو جدید است
    if "waiting_for_archive_name" in context.user_data:
        await handle_archive_name(update, context)
    # اگر کاربر در حال آپلود فایل است اما متن ارسال کرده
    elif "waiting_for_file" in context.user_data:
        await update.message.reply_text("لطفاً یک فایل ارسال کنید، نه متن.")
    else:
        await update.message.reply_text("لطفاً از منوی مدیریت استفاده کنید.")


# تابع اصلی
def main():
    init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    # اضافه کردن هندلرهای جدید
    application.add_handler(
        MessageHandler(filters.Regex("⚙️ تنظیمات"), handle_settings_button)
    )
    application.add_handler(
        CallbackQueryHandler(
            handle_settings_callback,
            pattern="^(settings_|back_to_|file_|archive_|enable_|disable_|set_time_)",
        )
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time_input), group=1
    )

    # هندلرهای قبلی
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(
        CallbackQueryHandler(
            handle_archive_callback, pattern="^(new_archive|open_arc_)"
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO,
            handle_file,
        )
    )
    application.add_handler(MessageHandler(filters.Regex("📋 لیست فایل‌ها"), list_files))
    application.add_handler(MessageHandler(filters.Regex("🗑 حذف فایل"), delete_file))
    application.add_handler(
        MessageHandler(filters.Regex("📦 آرشیو پست"), start_create_archive)
    )
    application.add_handler(
        MessageHandler(filters.Regex("👥 مدیریت ادمین‌ها"), manage_admins)
    )
    application.add_handler(
        MessageHandler(filters.Regex("📤 آپلود فایل جدید"), start_file_upload)
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )

    application.run_polling()


if __name__ == "__main__":
    main()
