import asyncio
import logging
import pickle
import sqlite3
import uuid
import aiohttp
import re

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
    InputMediaPhoto,
    InputMediaVideo,
    InputMediaDocument,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

BOT_TOKEN = "8339151235:AAHWAVBU0E0BFS9OGncjYXQwdU8XqHY83aQ"
ADMIN_IDS = [2120880112, 6357014606]
DEFAULT_SELF_DESTRUCT_TIME = 15


# جداول جدید برای تنظیمات تبلیغاتی
def init_db():
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()

    # جدول فایل‌ها
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

    # جدول آرشیو
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

    # تنظیمات عمومی (مثلا برای خودتخریبی)
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

    # قفل کانال (عضویت اجباری)
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS locks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        entity_id INTEGER NOT NULL,
        required_channels BLOB,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    )

    # تبلیغات
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS ad_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        setting_key TEXT UNIQUE NOT NULL,
        setting_value TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS caption_ads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad_text TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS glass_buttons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        button_text TEXT NOT NULL,
        button_url TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    )

    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS banner_ads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        banner_type TEXT NOT NULL,
        banner_content TEXT NOT NULL,
        banner_file_id TEXT,
        display_time INTEGER DEFAULT 10,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
    )

    # 🔹 جدول جدید برای سین اجباری (Forced View)
    cursor.execute(
        """
    CREATE TABLE IF NOT EXISTS forced_view_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        entity_id INTEGER NOT NULL,
        channel_id TEXT NOT NULL,
        channel_username TEXT NOT NULL,
        post_url TEXT NOT NULL,
        view_time INTEGER DEFAULT 10,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(entity_type, entity_id)
    )
    """
    )

    conn.commit()
    conn.close()

def is_admin(user_id):
    return user_id in ADMIN_IDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    bot_username = context.bot.username

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

            context.user_data["lock_entity"] = {"type": "file", "id": file_db_id}

            await send_single_file(update, context, file_data)

            if self_destruct:
                # warning_msg = (
                #     f"⚠️ این فایل دارای تخریب خودکار است!\n\n"
                #     "📌 لطفاً بلافاصله فایل را به Saved Messages خود منتقل کنید تا از دست نرود."
                # )
                pass
        else:
            await update.message.reply_text("❌ فایل مورد نظر یافت نشد.")

    elif args and args[0].startswith("arc_"):
        archive_code = args[0][4:]

        conn = sqlite3.connect("file_bot.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM archives WHERE archive_code = ?", (archive_code,)
        )
        archive_data = cursor.fetchone()
        conn.close()

        if archive_data:
            archive_id = archive_data[0]
            context.user_data["lock_entity"] = {"type": "archive", "id": archive_id}
            await send_archive_files(update, context, archive_code)
        else:
            await update.message.reply_text("❌ آرشیو مورد نظر یافت نشد.")
    else:
        if is_admin(user_id):
            await admin_panel(update, context)
        else:
            await update.message.reply_text(
                "سلام! به ربات ما خوش آمدید.\n\n"
                "برای دریافت فایل از لینک اختصاصی آن استفاده کنید."
            )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

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

async def admin_panel_from_query(query, context):
    await query.message.delete()
    await admin_panel(query, context)

async def start_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    context.user_data["waiting_for_file"] = True

    if "waiting_for_archive_name" in context.user_data:
        del context.user_data["waiting_for_archive_name"]

    await update.message.reply_text("لطفاً فایل خود را ارسال کنید.")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    is_waiting = "waiting_for_file" in context.user_data
    is_archive = "current_archive" in context.user_data

    if not is_waiting and not is_archive:
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

    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO files (file_id, file_name, file_type, caption, caption_entities, unique_code, archive_id, self_destruct) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            file_id,
            file_name,
            file_type,
            caption,
            entities_blob,
            unique_code,
            archive_id,
            1,  # فعال کردن تخریب خودکار به طور پیش‌فرض
        ),
    )
    conn.commit()
    conn.close()

    if is_waiting:
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


async def start_create_archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    if "waiting_for_file" in context.user_data:
        del context.user_data["waiting_for_file"]

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

async def handle_archive_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    data = query.data

    if data == "new_archive":
        context.user_data["waiting_for_archive_name"] = True
        await query.message.reply_text("لطفاً یک نام برای آرشیو جدید وارد کنید:")
        return

    if data.startswith("open_arc_"):
        archive_code = data[9:]

        context.user_data["current_archive"] = archive_code

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

async def send_single_file(
    update: Update, context: ContextTypes.DEFAULT_TYPE, file_data
):
    file_db_id = file_data[0]
    file_id = file_data[1]

    # 🔹 بررسی سین اجباری
    can_access = await check_forced_view(
        update.effective_user.id,
        "file",
        file_db_id,
        context,
        update
    )
    if not can_access:
        return

    # 🔹 بررسی عضویت در کانال‌های اجباری
    required_channels = get_required_channels("file", file_db_id)
    if required_channels and not await check_user_channels(
        update.effective_user.id, required_channels, context
    ):
        await prompt_user_to_join_channels(update, context, required_channels)
        return

    # مشخصات فایل
    file_type = file_data[3]
    caption = file_data[4] or ""

    caption_entities = None
    if file_data[5] and isinstance(file_data[5], (bytes, bytearray)):
        try:
            caption_entities = pickle.loads(file_data[5])
        except Exception as e:
            logging.error(f"Error loading caption entities: {e}")

    message = None
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

        # 🔹 بررسی خودتخریبی فایل
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

async def send_archive_files(
    update: Update, context: ContextTypes.DEFAULT_TYPE, archive_code
):
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()

    # گرفتن اطلاعات آرشیو
    cursor.execute(
        "SELECT id, archive_name FROM archives WHERE archive_code = ?", (archive_code,)
    )
    archive_data = cursor.fetchone()
    if not archive_data:
        await update.message.reply_text("آرشیو مورد نظر یافت نشد.")
        conn.close()
        return

    archive_id, archive_name = archive_data

    # 🔹 بررسی سین اجباری
    can_access = await check_forced_view(
        update.effective_user.id,
        "archive",
        archive_id,
        context,
        update
    )
    if not can_access:
        conn.close()
        return

    # 🔹 بررسی عضویت در کانال‌های اجباری
    required_channels = get_required_channels("archive", archive_id)
    if required_channels and not await check_user_channels(
        update.effective_user.id, required_channels, context
    ):
        await prompt_user_to_join_channels(update, context, required_channels)
        conn.close()
        return

    # گرفتن فایل‌های آرشیو
    cursor.execute(
        "SELECT * FROM files WHERE archive_id = ? ORDER BY id", (archive_id,)
    )
    files_data = cursor.fetchall()
    conn.close()

    if not files_data:
        await update.message.reply_text("هیچ فایلی در این آرشیو یافت نشد.")
        return

    # پیام خوشامد آرشیو
    welcome_msg = await update.message.reply_text(f"📦 آرشیو: {archive_name}")
    message_ids = [welcome_msg.message_id]

    # ارسال فایل‌ها
    for file_data in files_data:
        file_id = file_data[1]
        file_type = file_data[3]
        caption = file_data[4] or ""

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

    # 🔹 بررسی خودتخریبی
    if is_self_destruct_enabled("archive", archive_id):
        destruct_time = get_self_destruct_time("archive", archive_id)
        asyncio.create_task(
            self_destruct_messages(
                update.effective_chat.id, message_ids, context, destruct_time
            )
        )

async def handle_settings_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    keyboard = [
        [InlineKeyboardButton("⚙️ تخریب خودکار", callback_data="auto_destruct")],
        [InlineKeyboardButton("🔒 قفل", callback_data="lock_settings")],
        [InlineKeyboardButton("📢 تبلیغات", callback_data="ad_settings")],  # اضافه کردن تبلیغات
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "تنظیمات - لطفاً گزینه مورد نظر را انتخاب کنید:", reply_markup=reply_markup
    )

async def settings_menu_from_query(query, context):
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    keyboard = [
        [InlineKeyboardButton("⚙️ تخریب خودکار", callback_data="auto_destruct")],
        [InlineKeyboardButton("🔒 قفل", callback_data="lock_settings")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.edit_text(
        "تنظیمات - لطفاً گزینه مورد نظر را انتخاب کنید:", reply_markup=reply_markup
    )

async def handle_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    data = query.data

    # 🔹 تخریب خودکار
    if data == "auto_destruct":
        keyboard = [
            [InlineKeyboardButton("⚙️ فایل‌ها", callback_data="settings_file")],
            [InlineKeyboardButton("⚙️ آرشیوها", callback_data="settings_archive")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_settings")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            "تخریب خودکار - لطفاً گزینه مورد نظر را انتخاب کنید:",
            reply_markup=reply_markup,
        )

    # 🔹 قفل ساده
    elif data == "lock_settings":
        keyboard = [
            [InlineKeyboardButton("🔒 قفل ساده", callback_data="simple_lock")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_settings")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            "تنظیمات قفل - لطفاً گزینه مورد نظر را انتخاب کنید:",
            reply_markup=reply_markup,
        )

    elif data == "simple_lock":
        await show_simple_lock(query)

    # 🔹 تنظیمات فایل و آرشیو
    elif data == "settings_file":
        await show_file_settings(query)
    elif data == "settings_archive":
        await show_archive_settings(query)
    elif data == "back_to_settings":
        await settings_menu_from_query(query, context)
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

    # 🔹 قفل ساده روی فایل یا آرشیو
    elif data.startswith("lock_file_") or data.startswith("lock_archive_"):
        await handle_simple_lock(query, data, context)

    # 🔹 تبلیغات
    elif data == "ad_settings":
        await handle_ad_settings(query)
    elif data == "back_to_ad_settings":
        await handle_ad_settings(query)

    # 🔹 سین اجباری
    elif data == "forced_view_settings":
        await handle_forced_view_settings(query)
    elif data == "add_forced_view":
        await add_forced_view(update, context)
    elif data == "list_forced_view":
        await list_forced_view_settings(query)
    elif data.startswith("force_view_file_") or data.startswith("force_view_archive_"):
        await handle_force_view_selection(query, data, context)

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

async def enable_self_destruct_file(query, file_id):
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE files SET self_destruct = 1 WHERE id = ?", (file_id,))
    conn.commit()
    conn.close()

    await query.answer("تخریب خودکار فعال شد!")
    await handle_file_settings(query, f"file_{file_id}")


async def disable_self_destruct_file(query, file_id):
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE files SET self_destruct = 0 WHERE id = ?", (file_id,))
    conn.commit()
    conn.close()

    await query.answer("تخریب خودکار غیرفعال شد!")
    await handle_file_settings(query, f"file_{file_id}")


async def enable_self_destruct_archive(query, archive_id):
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE archives SET self_destruct = 1 WHERE id = ?", (archive_id,))
    conn.commit()
    conn.close()

    await query.answer("تخریب خودکار فعال شد!")
    await handle_archive_settings(query, f"archive_{archive_id}")


async def disable_self_destruct_archive(query, archive_id):
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE archives SET self_destruct = 0 WHERE id = ?", (archive_id,))
    conn.commit()
    conn.close()

    await query.answer("تخریب خودکار غیرفعال شد!")
    await handle_archive_settings(query, f"archive_{archive_id}")

async def handle_set_time(query, data, context):
    parts = data.split("_")
    entity_type = parts[2]  # file یا archive
    entity_id = int(parts[3])

    context.user_data["setting_time_for"] = {"type": entity_type, "id": entity_id}
    context.user_data["waiting_for_time"] = True

    await query.message.edit_text(
        "لطفاً زمان تخریب خودکار را به ثانیه وارد کنید:\n\n" "مثال: 30 (برای ۳۰ ثانیه)"
    )


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

        cursor.execute(
            "DELETE FROM settings WHERE entity_type = ? AND entity_id = ?",
            (entity_type, entity_id),
        )

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

async def self_destruct_messages(chat_id, message_ids, context, delay_seconds):
    try:
        await asyncio.sleep(delay_seconds)

        for msg_id in message_ids:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception as e:
                # اگر پیام قبلاً حذف شده، خطا را نادیده بگیر
                if "message to delete not found" not in str(e).lower():
                    logging.error(f"Error deleting message {msg_id}: {e}")

    except Exception as e:
        logging.error(f"Error in self_destruct: {e}")

async def show_simple_lock(query):
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()

    cursor.execute("SELECT id, file_name FROM files ORDER BY id DESC LIMIT 10")
    files = cursor.fetchall()

    cursor.execute("SELECT id, archive_name FROM archives ORDER BY id DESC LIMIT 10")
    archives = cursor.fetchall()

    conn.close()

    keyboard = []
    for file in files:
        file_id, file_name = file
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"📁 {file_name}", callback_data=f"lock_file_{file_id}"
                )
            ]
        )

    for archive in archives:
        archive_id, archive_name = archive
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"📦 {archive_name}", callback_data=f"lock_archive_{archive_id}"
                )
            ]
        )

    keyboard.append(
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_settings")]
    )

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        "قفل ساده - لطفاً فایل یا آرشیو را انتخاب کنید:", reply_markup=reply_markup
    )

async def handle_simple_lock(query, data, context):
    if data.startswith("lock_file_"):
        entity_type = "file"
        entity_id = int(data[10:])
    else:
        entity_type = "archive"
        entity_id = int(data[13:])

    context.user_data["lock_entity"] = {"type": entity_type, "id": entity_id}
    context.user_data["waiting_for_channels"] = True

    await query.message.edit_text(
        "لطفاً لیست چنل‌های مورد نظر برای دسترسی را وارد کنید، هر چنل با فاصله جدا شود:\n"
        "مثال: @channel1 @channel2 @channel3"
    )

def get_required_channels(entity_type, entity_id):
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT required_channels FROM locks WHERE entity_type = ? AND entity_id = ?",
        (entity_type, entity_id),
    )
    result = cursor.fetchone()
    conn.close()
    return pickle.loads(result[0]) if result else []

async def check_user_channels(user_id, required_channels, context):
    for ch in required_channels:
        try:
            member = await context.bot.get_chat_member(ch, user_id)
            if member.status not in ["left", "kicked"]:
                continue
            else:
                return False
        except Exception as e:
            logging.error(f"Error checking channel {ch}: {e}")
            return False
    return True


async def check_membership_via_api(user_id: int, channels: list[str]) -> bool:
    """
    بررسی عضویت کاربر در کانال‌ها با تماس به secure_bot API
    """
    url = "http://127.0.0.1:8000/check_user"
    headers = {"x-api-key": "supersecret"}
    payload = {"user_id": user_id, "channels": channels}

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                return False  # خطا در ارتباط با API
            data = await resp.json()
            return data.get("status") == "yes"

async def prompt_user_to_join_channels(update: Update, context, required_channels):
    """
    نمایش پیام هشدار با دکمه‌ها فقط یک بار
    """
    # اگر قبلاً پیام هشدار ارسال شده بود، چیزی نفرست
    if context.user_data.get("prompt_message_sent"):
        return

    keyboard = [
        [InlineKeyboardButton(f"🔗 {ch}", url=f"https://t.me/{ch.lstrip('@')}")]
        for ch in required_channels
    ]
    keyboard.append(
        [InlineKeyboardButton("✅ چک دوباره عضویت", callback_data="check_channels")]
    )
    reply_markup = InlineKeyboardMarkup(keyboard)

    # تشخیص نوع update
    if update.callback_query:
        message = update.callback_query.message
    else:
        message = update.message

    sent_msg = await message.reply_text(
        "⚠️ برای دسترسی به این فایل ابتدا باید عضو چنل‌های مشخص شده شوید.\n\n"
        "⏰ این پیام به طور خودکار پس از 15 ثانیه حذف خواهد شد.",
        reply_markup=reply_markup,
    )

    # ثبت اینکه پیام هشدار ارسال شده و ذخیره ID آن
    context.user_data["prompt_message_sent"] = True
    context.user_data["prompt_message_id"] = sent_msg.message_id
    context.user_data["prompt_chat_id"] = sent_msg.chat.id

    # شروع تایمر برای حذف خودکار پیام
    asyncio.create_task(
        delete_prompt_after_delay(context, sent_msg.chat.id, sent_msg.message_id)
    )


async def handle_channels_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "waiting_for_channels" not in context.user_data:
        return

    channels = update.message.text.strip().split()
    entity_info = context.user_data["lock_entity"]

    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM locks WHERE entity_type = ? AND entity_id = ?",
        (entity_info["type"], entity_info["id"]),
    )

    cursor.execute(
        "INSERT INTO locks (entity_type, entity_id, required_channels) VALUES (?, ?, ?)",
        (entity_info["type"], entity_info["id"], pickle.dumps(channels)),
    )

    conn.commit()
    conn.close()

    del context.user_data["waiting_for_channels"]
    del context.user_data["lock_entity"]

    await update.message.reply_text("قفل ساده با موفقیت اعمال شد.")

async def delete_prompt_after_delay(context, chat_id, message_id, delay=15):
    """حذف پیام درخواست عضویت پس از تاخیر مشخص"""
    try:
        await asyncio.sleep(delay)
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)

        # پاک کردن فقط اطلاعات پیام prompt از context، نه اطلاعات entity
        if "prompt_message_id" in context.user_data:
            context.user_data.pop("prompt_message_id", None)
        if "prompt_chat_id" in context.user_data:
            context.user_data.pop("prompt_chat_id", None)
        if "prompt_message_sent" in context.user_data:
            context.user_data.pop("prompt_message_sent", None)

    except Exception as e:
        logging.error(f"Error deleting prompt message: {e}")

async def handle_check_channels(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # بازیابی اطلاعات entity از context (اگر وجود دارد)
    entity_info = context.user_data.get("lock_entity")
    if not entity_info:
        await query.answer("❌ خطا: اطلاعات فایل یا آرشیو یافت نشد.", show_alert=True)
        return

    required_channels = get_required_channels(entity_info["type"], entity_info["id"])

    # بررسی عضویت
    is_member = await check_membership_via_api(user_id, required_channels)

    if is_member:
        await query.answer("✅ شما اکنون عضو همه چنل‌های لازم هستید.", show_alert=True)

        # حذف پیام درخواست عضویت (اگر وجود دارد)
        if (
            "prompt_message_id" in context.user_data
            and "prompt_chat_id" in context.user_data
        ):
            try:
                await context.bot.delete_message(
                    chat_id=context.user_data["prompt_chat_id"],
                    message_id=context.user_data["prompt_message_id"],
                )
            except Exception as e:
                logging.error(f"Error deleting prompt message: {e}")

        # حذف پیام اصلی که حاوی دکمه‌هاست (پیام callback)
        try:
            await query.message.delete()
        except Exception as e:
            logging.error(f"Error deleting query message: {e}")

        # پاک کردن فقط اطلاعات پیام prompt از context، نه اطلاعات entity
        context.user_data.pop("prompt_message_id", None)
        context.user_data.pop("prompt_chat_id", None)
        context.user_data.pop("prompt_message_sent", None)

        # ارسال فایل یا آرشیو
        conn = sqlite3.connect("file_bot.db")
        cursor = conn.cursor()
        if entity_info["type"] == "file":
            cursor.execute(
                "SELECT id, file_id, file_name, file_type, caption, caption_entities, self_destruct FROM files WHERE id = ?",
                (entity_info["id"],),
            )
            file_data = cursor.fetchone()
            if file_data:
                await send_single_file(update, context, file_data)
            else:
                # اگر فایل پیدا نشد، همچنان اطلاعات entity را حفظ نکن
                context.user_data.pop("lock_entity", None)
                await query.message.reply_text("❌ فایل مورد نظر یافت نشد.")
        elif entity_info["type"] == "archive":
            cursor.execute(
                "SELECT archive_code FROM archives WHERE id = ?", (entity_info["id"],)
            )
            archive_row = cursor.fetchone()
            if archive_row:
                await send_archive_files(update, context, archive_row[0])
            else:
                # اگر آرشیو پیدا نشد، همچنان اطلاعات entity را حفظ نکن
                context.user_data.pop("lock_entity", None)
                await query.message.reply_text("❌ آرشیو مورد نظر یافت نشد.")
        conn.close()

        # پس از ارسال محتوا، اطلاعات entity را پاک کنید
        context.user_data.pop("lock_entity", None)

    else:
        # نمایش alert فوری
        await query.answer(
            "⚠️ هنوز عضو همه چنل‌ها نیستید. لطفاً ابتدا عضو شوید و دوباره تلاش کنید.",
            show_alert=True,
        )

        # فقط اگر پیام هشدار اصلی هنوز وجود ندارد، پیام با دکمه‌ها را بفرست
        if not context.user_data.get("prompt_message_sent"):
            await prompt_user_to_join_channels(update, context, required_channels)

async def handle_ad_settings(query):
    keyboard = [
        [InlineKeyboardButton("🔍 سین اجباری", callback_data="forced_view_settings")],
        [InlineKeyboardButton("📝 تبلیغات کپشن", callback_data="caption_ads")],
        [InlineKeyboardButton("🔘 دکمه شیشه‌ای", callback_data="glass_buttons")],
        [InlineKeyboardButton("🖼 بنر تبلیغاتی", callback_data="banner_ads")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "تنظیمات تبلیغات - گزینه مورد نظر را انتخاب کنید:",
        reply_markup=reply_markup
    )

async def show_ad_settings_menu(query):
    keyboard = [
        [InlineKeyboardButton("🔍 سین اجباری", callback_data="forced_view_settings")],
        [InlineKeyboardButton("📝 تبلیغات کپشن", callback_data="caption_ads")],
        [InlineKeyboardButton("🔘 دکمه شیشه‌ای", callback_data="glass_buttons")],
        [InlineKeyboardButton("🖼 بنر تبلیغاتی", callback_data="banner_ads")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(
        "تنظیمات تبلیغات - گزینه مورد نظر را انتخاب کنید:",
        reply_markup=reply_markup
    )

async def handle_forced_view_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("➕ افزودن سین اجباری", callback_data="add_forced_view")],
        [InlineKeyboardButton("📋 لیست تنظیمات", callback_data="list_forced_view")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_ad_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.edit_text(
        "تنظیمات سین اجباری - گزینه مورد نظر را انتخاب کنید:",
        reply_markup=reply_markup
    )


# افزودن سین اجباری
async def add_forced_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # نمایش فایل‌ها و آرشیوها برای انتخاب
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, file_name FROM files ORDER BY id DESC LIMIT 10")
    files = cursor.fetchall()
    
    cursor.execute("SELECT id, archive_name FROM archives ORDER BY id DESC LIMIT 10")
    archives = cursor.fetchall()
    
    conn.close()
    
    keyboard = []
    for file in files:
        file_id, file_name = file
        keyboard.append([
            InlineKeyboardButton(
                f"📁 {file_name}", 
                callback_data=f"force_view_file_{file_id}"
            )
        ])
    
    for archive in archives:
        archive_id, archive_name = archive
        keyboard.append([
            InlineKeyboardButton(
                f"📦 {archive_name}", 
                callback_data=f"force_view_archive_{archive_id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="forced_view_settings")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.edit_text(
        "انتخاب فایل یا آرشیو برای سین اجباری:",
        reply_markup=reply_markup
    )

# پردازش انتخاب فایل/آرشیو برای سین اجباری
async def handle_force_view_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("force_view_file_"):
        entity_type = "file"
        entity_id = int(data[16:])
    else:
        entity_type = "archive"
        entity_id = int(data[19:])

    # ذخیره موقت برای دریافت آیدی کانال
    context.user_data["forced_view_entity"] = {
        "type": entity_type,
        "id": entity_id
    }
    context.user_data["waiting_for_channel_simple_id"] = True

    await query.message.edit_text(
        "لطفاً آیدی کانال را ارسال کنید تا دسترسی به این محتوا فعال شود:"
    )


# پردازش اطلاعات کانال
async def handle_channel_info_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "waiting_for_channel_simple_id" not in context.user_data:
        return

    channel_id = update.message.text.strip()  # حالا یک رشته ساده است
    entity_info = context.user_data["forced_view_entity"]

    # ذخیره در دیتابیس
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()

    # حذف تنظیمات قبلی اگر وجود دارد
    cursor.execute(
        "DELETE FROM forced_view_settings WHERE entity_type = ? AND entity_id = ?",
        (entity_info["type"], entity_info["id"])
    )

    # افزودن تنظیمات جدید (فقط آیدی کانال به شکل رشته)
    cursor.execute(
        "INSERT INTO forced_view_settings (entity_type, entity_id, channel_id, channel_username, post_url) "
        "VALUES (?, ?, ?, '', '')",
        (entity_info["type"], entity_info["id"], channel_id)
    )

    conn.commit()
    conn.close()

    del context.user_data["waiting_for_channel_simple_id"]
    del context.user_data["forced_view_entity"]

    await update.message.reply_text("✅ تنظیمات سین اجباری با موفقیت ذخیره شد.")

# بررسی سین اجباری قبل از ارسال فایل
async def check_forced_view(user_id, entity_type, entity_id, context, update):
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT channel_id FROM forced_view_settings WHERE entity_type = ? AND entity_id = ?",
        (entity_type, entity_id)
    )
    setting = cursor.fetchone()
    conn.close()

    if not setting:
        return True  # هیچ سین اجباری نیست

    channel_id = setting[0]

    # کلید برای بررسی تأیید کاربر
    user_verified_key = f"forced_view_verified_{user_id}_{entity_type}_{entity_id}"
    if context.user_data.get(user_verified_key):
        return True  # قبلاً تأیید شده

    # اگر تأیید نشده، پیام بده
    keyboard = [
        [InlineKeyboardButton("✅ تأیید مشاهده", callback_data=f"confirm_view_{entity_type}_{entity_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = (
        f"⚠️ برای دسترسی به این محتوا، باید ابتدا سین انجام شود.\n\n"
        f"🔗 کانال: {channel_id}\n"
        "📌 پس از مشاهده کانال، روی دکمه 'تأیید مشاهده' کلیک کنید."
    )

    if update.callback_query:
        await update.callback_query.message.reply_text(message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)

    return False



# نمایش پیام سین اجباری با دکمه‌های شیشه‌ای
async def show_forced_view_prompt(update, context, channel_username, post_url, entity_type, entity_id):
    keyboard = [
        [InlineKeyboardButton("🔗 مشاهده پست", url=post_url)],
        [InlineKeyboardButton("✅ تأیید مشاهده", callback_data=f"confirm_view_{entity_type}_{entity_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = (
        "⚠️ برای دسترسی به این محتوا، باید در کانال عضو شده و پست مشخص شده را مشاهده کنید.\n\n"
        f"🔗 کانال: {channel_username}\n"
        "📌 پس از مشاهده پست، روی دکمه 'تأیید مشاهده' کلیک کنید."
    )
    
    if update.callback_query:
        await update.callback_query.message.reply_text(message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)

# پردازش تأیید مشاهده
async def handle_confirm_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    entity_type = data.split('_')[2]
    entity_id = int(data.split('_')[3])
    
    user_id = query.from_user.id
    
    # ذخیره تأیید کاربر
    user_verified_key = f"forced_view_verified_{user_id}_{entity_type}_{entity_id}"
    context.user_data[user_verified_key] = True
    
    # حذف پیام درخواست
    await query.message.delete()
    
    # ارسال محتوا
    if entity_type == "file":
        conn = sqlite3.connect("file_bot.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM files WHERE id = ?", (entity_id,)
        )
        file_data = cursor.fetchone()
        conn.close()
        
        if file_data:
            await send_single_file(update, context, file_data)
    else:
        conn = sqlite3.connect("file_bot.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT archive_code FROM archives WHERE id = ?", (entity_id,)
        )
        archive_data = cursor.fetchone()
        conn.close()
        
        if archive_data:
            await send_archive_files(update, context, archive_data[0])

async def list_forced_view_settings(query):
    conn = sqlite3.connect("file_bot.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT fvs.entity_type, fvs.entity_id, fvs.channel_username, fvs.post_url,
               CASE 
                   WHEN fvs.entity_type = 'file' THEN f.file_name
                   WHEN fvs.entity_type = 'archive' THEN a.archive_name
               END as entity_name
        FROM forced_view_settings fvs
        LEFT JOIN files f ON fvs.entity_type = 'file' AND fvs.entity_id = f.id
        LEFT JOIN archives a ON fvs.entity_type = 'archive' AND fvs.entity_id = a.id
    """)
    
    settings = cursor.fetchall()
    conn.close()
    
    if not settings:
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="forced_view_settings")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            "❌ هیچ تنظیمات سین اجباری وجود ندارد.",
            reply_markup=reply_markup
        )
        return
    
    message = "📋 لیست تنظیمات سین اجباری:\n\n"
    
    for setting in settings:
        entity_type, entity_id, channel_username, post_url, entity_name = setting
        message += f"📌 {entity_name} ({'فایل' if entity_type == 'file' else 'آرشیو'})\n"
        message += f"🔗 کانال: {channel_username}\n"
        message += f"📎 پست: {post_url}\n"
        message += f"🗑 /delete_forced_view_{entity_type}_{entity_id}\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="forced_view_settings")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.edit_text(message, reply_markup=reply_markup)

async def manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("شما دسترسی به این بخش را ندارید.")
        return

    admin_list = "\n".join([f"🆔 {admin_id}" for admin_id in ADMIN_IDS])
    await update.message.reply_text(f"لیست ادمین‌ها:\n{admin_list}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    if "waiting_for_archive_name" in context.user_data:
        await handle_archive_name(update, context)
    elif "waiting_for_file" in context.user_data:
        await update.message.reply_text("لطفاً یک فایل ارسال کنید، نه متن.")
    else:
        await update.message.reply_text("لطفاً از منوی مدیریت استفاده کنید.")


def main():
    init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    # =========================
    # 🔹 هندلرهای سین اجباری
    # =========================
    application.add_handler(CallbackQueryHandler(handle_forced_view_settings, pattern="^forced_view_settings$"))
    application.add_handler(CallbackQueryHandler(add_forced_view, pattern="^add_forced_view$"))
    application.add_handler(CallbackQueryHandler(handle_force_view_selection, pattern="^force_view_(file|archive)_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_channel_info_input), group=3)
    application.add_handler(CallbackQueryHandler(handle_confirm_view, pattern="^confirm_view_(file|archive)_"))

    # =========================
    # 🔹 هندلرهای تبلیغات
    # =========================
    application.add_handler(CallbackQueryHandler(handle_check_channels, pattern="^check_channels$"))

    # =========================
    # 🔹 هندلرهای تنظیمات
    # =========================
    application.add_handler(MessageHandler(filters.Regex("⚙️ تنظیمات"), handle_settings_button))
    application.add_handler(CallbackQueryHandler(handle_settings_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time_input), group=1)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_channels_input), group=2)

    # =========================
    # 🔹 دستورات عمومی
    # =========================
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))

    # =========================
    # 🔹 مدیریت آرشیو و فایل‌ها
    # =========================
    application.add_handler(CallbackQueryHandler(handle_archive_callback, pattern="^(new_archive|open_arc_)"))
    application.add_handler(
        MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO, handle_file)
    )
    application.add_handler(MessageHandler(filters.Regex("📋 لیست فایل‌ها"), list_files))
    application.add_handler(MessageHandler(filters.Regex("🗑 حذف فایل"), delete_file))
    application.add_handler(MessageHandler(filters.Regex("📦 آرشیو پست"), start_create_archive))
    application.add_handler(MessageHandler(filters.Regex("👥 مدیریت ادمین‌ها"), manage_admins))
    application.add_handler(MessageHandler(filters.Regex("📤 آپلود فایل جدید"), start_file_upload))

    # =========================
    # 🔹 هندلر پیش‌فرض (متن‌ها)
    # =========================
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # =========================
    # 🔹 اجرای ربات
    # =========================
    application.run_polling()

if __name__ == "__main__":
    main()
