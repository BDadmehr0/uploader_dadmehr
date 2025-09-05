import html
import logging
import os
import pickle  # اضافه کردن ماژول pickle
import re
import sqlite3
import uuid
from datetime import datetime

from telegram import (InlineKeyboardButton, InlineKeyboardMarkup,
                      KeyboardButton, ReplyKeyboardMarkup, Update)
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

# تنظیمات لاگ
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# توکن ربات
BOT_TOKEN = "8339151235:AAHWAVBU0E0BFS9OGncjYXQwdU8XqHY83aQ"

# لیست ادمین‌ها (ایدی‌های عددی)
ADMIN_IDS = [2120880112]


# ایجاد اتصال به دیتابیس
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
        archive_id INTEGER DEFAULT NULL
    )
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS archives (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        archive_name TEXT NOT NULL,
        archive_code TEXT UNIQUE NOT NULL,
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
    if "waiting_for_archive_name" in context.user_data:
        del context.user_data["waiting_for_archive_name"]
    if "waiting_for_file" in context.user_data:
        del context.user_data["waiting_for_file"]

    keyboard = [
        [KeyboardButton("📤 آپلود فایل جدید"), KeyboardButton("📦 آرشیو پست")],
        [KeyboardButton("📋 لیست فایل‌ها"), KeyboardButton("🗑 حذف فایل")],
        [KeyboardButton("👥 مدیریت ادمین‌ها")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "پنل مدیریت - گزینه مورد نظر را انتخاب کنید:", reply_markup=reply_markup
    )


# شروع ایجاد آرشیو پست
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


# پردازش انتخاب آرشیو
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


# پردازش نام آرشیو و ایجاد آن
async def handle_archive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    # بررسی آیا کاربر در حال ایجاد آرشیو جدید است
    if "waiting_for_archive_name" not in context.user_data:
        await update.message.reply_text(
            "لطفاً ابتدا از منو گزینه '📦 آرشیو پست' را انتخاب کرده و سپس 'ایجاد آرشیو جدید' را بزنید."
        )
        return

    archive_name = update.message.text.strip()
    archive_code = str(uuid.uuid4()).replace("-", "")[:12]

    # ذخیره آرشیو در دیتابیس
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO archives (archive_name, archive_code) VALUES (?, ?)",
        (archive_name, archive_code),
    )
    conn.commit()
    conn.close()

    # حذف وضعیت انتظار برای نام آرشیو
    del context.user_data["waiting_for_archive_name"]

    bot_username = context.bot.username
    archive_link = f"https://t.me/{bot_username}?start=arc_{archive_code}"

    await update.message.reply_text(
        f"✅ آرشیو با موفقیت ایجاد شد!\n\n"
        f"نام آرشیو: {archive_name}\n"
        f"لینک اختصاصی:\n`{archive_link}`\n\n"
        f"اکنون می‌توانید فایل‌ها را به این آرشیو اضافه کنید.",
        parse_mode="Markdown",
    )


# مدیریت فایل‌های ارسالی توسط ادمین
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    if "waiting_for_file" not in context.user_data:
        await update.message.reply_text(
            "لطفاً ابتدا از منو گزینه '📤 آپلود فایل جدید' را انتخاب کنید."
        )
        return

    message = update.message

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
    if "current_archive" in context.user_data:
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

    # ذخیره اطلاعات فایل در دیتابیس
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO files (file_id, file_name, file_type, caption, caption_entities, unique_code, archive_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
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

    del context.user_data["waiting_for_file"]

    bot_username = context.bot.username
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


# ارسال فایل‌های یک آرشیو
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

    await update.message.reply_text(f"📦 آرشیو: {archive_name}")

    for file_data in files_data:
        await send_single_file(update, context, file_data)


# ارسال فایل تکی با حفظ فرمت و اسپویل
async def send_single_file(
    update: Update, context: ContextTypes.DEFAULT_TYPE, file_data
):
    file_id = file_data[1]
    file_type = file_data[3]
    caption = file_data[4] or ""

    # بازیابی caption_entities از دیتابیس
    caption_entities = None
    if file_data[5]:  # ستون caption_entities (ایندکس 5)
        try:
            caption_entities = pickle.loads(file_data[5])
        except Exception as e:
            logging.error(f"Error loading caption entities: {e}")

    try:
        if file_type == "document":
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=file_id,
                caption=caption,
                caption_entities=caption_entities,
            )
        elif file_type == "video":
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=file_id,
                caption=caption,
                caption_entities=caption_entities,
                has_spoiler=True,
            )
        elif file_type == "audio":
            await context.bot.send_audio(
                chat_id=update.effective_chat.id,
                audio=file_id,
                caption=caption,
                caption_entities=caption_entities,
            )
        elif file_type == "photo":
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=file_id,
                caption=caption,
                caption_entities=caption_entities,
                has_spoiler=True,
            )
    except Exception as e:
        logging.error(f"Error sending file: {e}")
        await update.message.reply_text("خطا در ارسال فایل.")


# مدیریت دستور /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if args:
        if args[0].startswith("get_"):
            unique_code = args[0][4:]

            conn = sqlite3.connect("file_bot.db")
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM files WHERE unique_code = ?", (unique_code,))
            file_data = cursor.fetchone()
            conn.close()

            if file_data:
                await send_single_file(update, context, file_data)
            else:
                await update.message.reply_text("فایل مورد نظر یافت نشد.")

        elif args[0].startswith("arc_"):
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


# نمایش لیست فایل‌ها
async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM files ORDER BY id DESC")
    files = cursor.fetchall()
    conn.close()

    if not files:
        await update.message.reply_text("هیچ فایلی وجود ندارد.")
        return

    bot_username = context.bot.username
    message = "📋 لیست فایل‌ها:\n\n"

    for file in files:
        (
            file_id,
            file_name,
            file_type,
            caption,
            caption_entities,
            created_at,
            unique_code,
            archive_id,
        ) = (file[0], file[2], file[3], file[4], file[5], file[6], file[7], file[8])
        file_link = f"https://t.me/{bot_username}?start=get_{unique_code}"

        if archive_id:
            conn = sqlite3.connect("file_bot.db")
            cursor = conn.cursor()
            cursor.execute(
                "SELECT archive_name FROM archives WHERE id = ?", (archive_id,)
            )
            archive_data = cursor.fetchone()
            archive_name = archive_data[0] if archive_data else "نامشخص"
            conn.close()
            message += f"📁 {file_name} (در آرشیو: {archive_name})\n🔗 {file_link}\n📅 {created_at}\n\n"
        else:
            message += f"📁 {file_name}\n🔗 {file_link}\n📅 {created_at}\n\n"

    await update.message.reply_text(message)


# حذف فایل
async def delete_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    await update.message.reply_text("این قابلیت به زودی اضافه خواهد شد.")


# مدیریت ادمین‌ها
async def manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    admin_list = "\n".join([f"🆔 {admin_id}" for admin_id in ADMIN_IDS])
    await update.message.reply_text(f"لیست ادمین‌ها:\n{admin_list}")


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
