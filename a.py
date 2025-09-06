# تابع بررسی ادمین
def is_admin(user_id):
    return user_id in ADMIN_IDS


# توابع مدیریت تبلیغات


# تغییرات در تابع ارسال فایل


# اضافه کردن هندلرهای جدید
def main():
    init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    # هندلرهای موجود
    application.add_handler(
        CallbackQueryHandler(handle_check_channels, pattern="^check_channels$")
    )
    application.add_handler(
        MessageHandler(filters.Regex("⚙️ تنظیمات"), handle_settings_button)
    )
    application.add_handler(CallbackQueryHandler(handle_settings_callback))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time_input), group=1
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_channels_input), group=2
    )

    # هندلرهای جدید برای تبلیغات
    application.add_handler(
        MessageHandler(filters.Regex("📢 تبلیغات"), ad_settings_panel)
    )
    application.add_handler(
        CallbackQueryHandler(handle_forced_view_settings, pattern="^ad_forced_view$")
    )
    application.add_handler(
        CallbackQueryHandler(
            handle_forced_entity_selection, pattern="^forced_(file|archive)_"
        )
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_channel_post_input),
        group=3,
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_view_time_input), group=4
    )
    application.add_handler(
        CallbackQueryHandler(handle_view_confirmation, pattern="^view_confirmed$")
    )

    # هندلرهای باقی مانده
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
