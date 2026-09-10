import json
import os
import logging
import threading
from flask import Flask
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# ----------------- Flask Keep-Alive Server -----------------
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is alive and running!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# ----------------- Configuration & Variables -----------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8539162576:AAEGk8ooZssZ91Mc7Uv2DlYPvKLOHQtJyIQ")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8744592769"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyAQ.Ab8RN6KUiJjtaJJQTtBhkzZ5H61DWmtXcNYe8KcBU6kZ9KiJtA")

DB_FILE = "database.json"

# Setup AI Model
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    ai_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    ai_model = None

user_quiz_state = {}

# Admin Conversation States
SELECT_ACTION, SELECT_TYPE, SELECT_SUBJECT, INPUT_YEAR_TYPE, INPUT_LEC_NUM, UPLOAD_FILE, DELETE_LEC_NUM = range(7)

# ----------------- Database Handlers -----------------
def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading JSON: {e}")
            return {"recordings": {}, "sheets": {}, "exams": {}}
    return {"recordings": {}, "sheets": {}, "exams": {}}

def save_data(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving JSON: {e}")

data_db = load_data()


# =====================================================================
# 1. واجهة الطالب (STUDENT INTERFACE - ARABIC)
# =====================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎙 التسجيلات الصوتية", callback_data="cat_recordings")],
        [InlineKeyboardButton("📚 الشيتات والمذكرات", callback_data="cat_sheets")],
        [InlineKeyboardButton("📝 الامتحانات السابقة", callback_data="cat_exams")],
        [InlineKeyboardButton("📬 تواصل عبر مجهول", callback_data="cat_anonymous")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "مرحباً بك في بوت المكتبة الأكاديمية! اختر من القائمة التالية:"
    
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=reply_markup)

async def student_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if data == "main_menu":
        await query.answer()
        await start(update, context)
        return

    # ---------------- قسم التسجيلات ----------------
    if data == "cat_recordings":
        await query.answer()
        keyboard = [
            [InlineKeyboardButton("القانون المدني", callback_data="rec_civil")],
            [InlineKeyboardButton("القانون الجنائي", callback_data="rec_criminal")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")]
        ]
        await query.message.edit_text("🎙 **قسم التسجيلات الصوتية**\nاختر المادة المطلوبة:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("rec_"):
        await query.answer()
        subject = data.split("_")[1]
        subject_data = data_db.get("recordings", {}).get(subject, {})
        
        if not subject_data:
            keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="cat_recordings")]]
            await query.message.edit_text("⚠️ لا توجد تسجيلات متوفرة لهذه المادة حالياً.", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        available_lecs = sorted(subject_data.keys(), key=lambda x: int(x) if x.isdigit() else x)
        keyboard = []
        row = []
        for lec in available_lecs:
            row.append(InlineKeyboardButton(f"محاضرة {lec}", callback_data=f"getaudio_{subject}_{lec}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
            
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="cat_recordings")])
        await query.message.edit_text("اختر المحاضرة للاستماع إليها:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("getaudio_"):
        await query.answer()
        _, subject, lec_num = data.split("_")
        file_id = data_db.get("recordings", {}).get(subject, {}).get(lec_num)
        
        if file_id:
            await query.message.reply_audio(audio=file_id, caption=f"🎙 تسجيل المحاضرة {lec_num} ({subject})")
        else:
            await query.message.reply_text(f"⚠️ المحاضرة {lec_num} غير متوفرة حالياً.")

    # ---------------- قسم الشيتات ----------------
    elif data == "cat_sheets":
        await query.answer()
        keyboard = [
            [InlineKeyboardButton("القانون المدني", callback_data="sheet_civil")],
            [InlineKeyboardButton("القانون الجنائي", callback_data="sheet_criminal")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")]
        ]
        await query.message.edit_text("📚 **قسم الشيتات والمذكرات**\nاختر المادة المطلوبة:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("sheet_"):
        await query.answer()
        subject = data.split("_")[1]
        subject_data = data_db.get("sheets", {}).get(subject, {})
        
        if not subject_data:
            keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="cat_sheets")]]
            await query.message.edit_text("⚠️ لا توجد شيتات متوفرة لهذه المادة حالياً.", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        available_lecs = sorted(subject_data.keys(), key=lambda x: int(x) if x.isdigit() else x)
        keyboard = []
        row = []
        for lec in available_lecs:
            row.append(InlineKeyboardButton(f"شيت {lec}", callback_data=f"getsheet_{subject}_{lec}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
            
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="cat_sheets")])
        await query.message.edit_text("اختر الشيت لعرضه:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("getsheet_"):
        await query.answer()
        _, subject, lec_num = data.split("_")
        file_id = data_db.get("sheets", {}).get(subject, {}).get(lec_num)
        
        keyboard = [
            [InlineKeyboardButton("🤖 اختبار الذكاء الاصطناعي", callback_data=f"ai_quiz_{subject}_{lec_num}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"sheet_{subject}")]
        ]
        
        if file_id:
            try:
                await query.message.reply_photo(
                    photo=file_id, 
                    caption=f"🖼 شيت المحاضرة {lec_num} ({subject})",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception:
                await query.message.reply_document(
                    document=file_id, 
                    caption=f"📄 شيت المحاضرة {lec_num} ({subject})",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        else:
            await query.message.reply_text(
                f"⚠️ الشيت الخاص بالمحاضرة {lec_num} غير مرفوع، ولكن يمكنك بدء اختبار الذكاء الاصطناعي:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    # ---------------- قسم اختبار الذكاء الاصطناعي ----------------
    elif data.startswith("ai_quiz_"):
        await query.answer()
        if not ai_model:
            await query.message.reply_text("⚠️ خيار الذكاء الاصطناعي غير مفعل حالياً.")
            return

        _, subject, lec_num = data.split("_")
        user_id = query.from_user.id
        
        await query.message.reply_text("⏳ جاري توليد سؤال مقالي بناءً على المحاضرة...")

        try:
            prompt = f"قم بتوليد سؤال مقالي دراسي مباشر واحد فقط لمادة {subject} المحاضرة {lec_num}. لا تضف أي إجابات."
            response = ai_model.generate_content(prompt)
            question = response.text

            user_quiz_state[user_id] = {
                "subject": subject,
                "lecture": lec_num,
                "question": question
            }

            await query.message.reply_text(
                f"📝 **سؤال المحاضرة {lec_num} ({subject}):**\n\n{question}\n\n✍️ **اكتب إجابتك النصية أسفل الرسالة لتصحيحها:**",
                parse_mode="Markdown"
            )
        except Exception:
            await query.message.reply_text("❌ حدث خطأ أثناء الاتصال بالذكاء الاصطناعي.")

    # ---------------- قسم الامتحانات السابقة ----------------
    elif data == "cat_exams":
        await query.answer()
        keyboard = [
            [InlineKeyboardButton("2023", callback_data="exyear_2023")],
            [InlineKeyboardButton("2024", callback_data="exyear_2024")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")]
        ]
        await query.message.edit_text("📝 **الامتحانات السابقة**\nاختر السنة الدراسية:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data.startswith("exyear_"):
        await query.answer()
        year = data.split("_")[1]
        keyboard = [
            [InlineKeyboardButton("القانون المدني", callback_data=f"exsub_{year}_civil")],
            [InlineKeyboardButton("القانون الجنائي", callback_data=f"exsub_{year}_criminal")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="cat_exams")]
        ]
        await query.message.edit_text(f"امتحانات سنة {year} - اختر المادة:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("exsub_"):
        await query.answer()
        _, year, subject = data.split("_")
        keyboard = [
            [InlineKeyboardButton("امتحان جزئي", callback_data=f"getexam_{year}_{subject}_mid")],
            [InlineKeyboardButton("امتحان نهائي", callback_data=f"getexam_{year}_{subject}_final")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"exyear_{year}")]
        ]
        await query.message.edit_text("اختر نوع الامتحان:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("getexam_"):
        await query.answer()
        _, year, subject, exam_type = data.split("_")
        type_str = "جزئي" if exam_type == "mid" else "نهائي"
        
        file_key = f"{year}_{subject}_{exam_type}"
        file_id = data_db.get("exams", {}).get(file_key)

        if file_id:
            try:
                await query.message.reply_document(document=file_id, caption=f"📁 نموذج امتحان {subject} - سنة {year} ({type_str})")
            except Exception:
                await query.message.reply_photo(photo=file_id, caption=f"📁 نموذج امتحان {subject} - سنة {year} ({type_str})")
        else:
            await query.message.reply_text(f"⚠️ نموذج الامتحان لمادة {subject} لسنة {year} ({type_str}) غير متوفر حالياً.")

    # ---------------- قسم التواصل المجهول ----------------
    elif data == "cat_anonymous":
        await query.answer()
        keyboard = [
            [InlineKeyboardButton("✉️ إرسال رسالة مجهولة", url="https://t.me/majho1bot")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")]
        ]
        await query.message.edit_text(
            "📬 **تواصل عبر مجهول**\n\nيمكنك إرسال استفساراتك أو ملاحظاتك عبر الرابط التالي:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

async def handle_student_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in user_quiz_state:
        if not ai_model:
            await update.message.reply_text("⚠️ تصحيح الذكاء الاصطناعي معطل حالياً.")
            return

        state = user_quiz_state[user_id]
        user_answer = update.message.text
        await update.message.reply_text("🔍 جاري تقييم وتصحيح إجابتك...")

        try:
            prompt = f"أنت مصحح أكاديمي.\nالسؤال: {state['question']}\nإجابة الطالب: {user_answer}\nقم بإعطاء درجة مئوية وتصحيح مختصر جداً باللغة العربية."
            response = ai_model.generate_content(prompt)
            await update.message.reply_text(f"📊 **نتيجة التقييم:**\n\n{response.text}", parse_mode="Markdown")
        except Exception:
            await update.message.reply_text("❌ حدث خطأ أثناء تقييم الإجابة.")

        del user_quiz_state[user_id]


# =====================================================================
# 2. ADMIN CONTROL PANEL (ENGLISH INTERFACE)
# =====================================================================

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text(f"⛔ Access Denied. Your User ID is: {user_id}")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("📤 Upload Content", callback_data="action_upload")],
        [InlineKeyboardButton("🗑 Delete Content", callback_data="action_delete")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_admin")]
    ]
    await update.message.reply_text("⚙️ **Admin Control Panel**\nSelect an action:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return SELECT_ACTION

async def admin_select_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_admin":
        await query.message.edit_text("❌ Action canceled.")
        return ConversationHandler.END

    action = query.data.split("_")[1]
    context.user_data['admin_action'] = action

    keyboard = [
        [InlineKeyboardButton("🎙 Recordings", callback_data="type_recordings")],
        [InlineKeyboardButton("🖼 Sheets", callback_data="type_sheets")],
        [InlineKeyboardButton("📝 Past Exams", callback_data="type_exams")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_admin")]
    ]
    await query.message.edit_text("📂 Select Category:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_TYPE

async def admin_select_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_admin":
        await query.message.edit_text("❌ Action canceled.")
        return ConversationHandler.END

    content_type = query.data.split("_")[1]
    context.user_data['upload_type'] = content_type

    keyboard = [
        [InlineKeyboardButton("Civil Law (civil)", callback_data="sub_civil")],
        [InlineKeyboardButton("Criminal Law (criminal)", callback_data="sub_criminal")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_admin")]
    ]
    await query.message.edit_text("📂 Select Subject:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_SUBJECT

async def admin_select_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_admin":
        await query.message.edit_text("❌ Action canceled.")
        return ConversationHandler.END

    subject = query.data.split("_")[1]
    context.user_data['upload_subject'] = subject
    content_type = context.user_data.get('upload_type')
    action = context.user_data.get('admin_action')

    if content_type == "exams":
        keyboard = [
            [InlineKeyboardButton("2023 - Midterm", callback_data="exinfo_2023_mid")],
            [InlineKeyboardButton("2023 - Final", callback_data="exinfo_2023_final")],
            [InlineKeyboardButton("2024 - Midterm", callback_data="exinfo_2024_mid")],
            [InlineKeyboardButton("2024 - Final", callback_data="exinfo_2024_final")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_admin")]
        ]
        await query.message.edit_text("📝 Select Exam Year & Type:", reply_markup=InlineKeyboardMarkup(keyboard))
        return INPUT_YEAR_TYPE

    if action == "delete":
        available = data_db.get(content_type, {}).get(subject, {})
        if not available:
            await query.message.edit_text(f"⚠️ No content found for `{subject}`.", parse_mode="Markdown")
            return ConversationHandler.END
            
        lecs_str = ", ".join(sorted(available.keys(), key=lambda x: int(x) if x.isdigit() else x))
        await query.message.edit_text(f"🗑 Available lectures: `{lecs_str}`\nType the lecture number to delete:", parse_mode="Markdown")
        return DELETE_LEC_NUM
    else:
        await query.message.edit_text("📖 Enter Lecture Number (e.g., 1, 2, 3):")
        return INPUT_LEC_NUM

async def admin_input_year_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel_admin":
        await query.message.edit_text("❌ Action canceled.")
        return ConversationHandler.END

    _, year, exam_type = query.data.split("_")
    subject = context.user_data['upload_subject']
    file_key = f"{year}_{subject}_{exam_type}"
    context.user_data['exam_key'] = file_key

    action = context.user_data.get('admin_action')

    if action == "delete":
        if file_key in data_db.get("exams", {}):
            del data_db["exams"][file_key]
            save_data(data_db)
            await query.message.edit_text(f"🗑 Deleted exam record: `{file_key}`.", parse_mode="Markdown")
        else:
            await query.message.edit_text(f"❌ Exam record `{file_key}` not found.", parse_mode="Markdown")
        return ConversationHandler.END
    else:
        await query.message.edit_text(f"📤 Please upload the Exam File (PDF/Image) for `{file_key}`:", parse_mode="Markdown")
        return UPLOAD_FILE

async def admin_input_lecture(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lec_num = update.message.text.strip()
    if not lec_num.isdigit():
        await update.message.reply_text("⚠️ Please enter a valid lecture number.")
        return INPUT_LEC_NUM

    context.user_data['upload_lec'] = lec_num
    await update.message.reply_text(f"📤 Upload the file/audio for Lecture {lec_num}:")
    return UPLOAD_FILE

async def admin_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content_type = context.user_data['upload_type']
    file_id = None

    if content_type == "exams":
        file_key = context.user_data['exam_key']
        if update.message.document:
            file_id = update.message.document.file_id
        elif update.message.photo:
            file_id = update.message.photo[-1].file_id

        if not file_id:
            await update.message.reply_text("⚠️ Invalid file type. Please send a Document or Image.")
            return UPLOAD_FILE

        if "exams" not in data_db:
            data_db["exams"] = {}
            
        data_db["exams"][file_key] = file_id
        save_data(data_db)
        await update.message.reply_text(f"✅ Successfully uploaded and saved Exam `{file_key}`!", parse_mode="Markdown")
        return ConversationHandler.END

    subject = context.user_data['upload_subject']
    lec_num = context.user_data['upload_lec']

    if content_type == "recordings":
        if update.message.audio:
            file_id = update.message.audio.file_id
        elif update.message.voice:
            file_id = update.message.voice.file_id
        elif update.message.document:
            file_id = update.message.document.file_id
    else:
        if update.message.photo:
            file_id = update.message.photo[-1].file_id
        elif update.message.document:
            file_id = update.message.document.file_id

    if not file_id:
        await update.message.reply_text("⚠️ Invalid file format. Please upload the appropriate file.")
        return UPLOAD_FILE

    if content_type not in data_db:
        data_db[content_type] = {}
    if subject not in data_db[content_type]:
        data_db[content_type][subject] = {}
        
    data_db[content_type][subject][lec_num] = file_id
    save_data(data_db)

    await update.message.reply_text("✅ Successfully saved to database!")
    return ConversationHandler.END

async def admin_delete_lecture(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lec_num = update.message.text.strip()
    content_type = context.user_data['upload_type']
    subject = context.user_data['upload_subject']

    if subject in data_db.get(content_type, {}) and lec_num in data_db[content_type][subject]:
        del data_db[content_type][subject][lec_num]
        save_data(data_db)
        await update.message.reply_text(f"🗑 Lecture `{lec_num}` deleted successfully.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Lecture number not found.")

    return ConversationHandler.END

async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text("❌ Operation canceled.")
    else:
        await update.message.reply_text("❌ Operation canceled.")
    return ConversationHandler.END


# =====================================================================
# 3. MAIN BOT EXECUTION
# =====================================================================

if __name__ == '__main__':
    # Start Flask Server in background thread for UptimeRobot Ping
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    admin_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('admin', admin_start)],
        states={
            SELECT_ACTION: [CallbackQueryHandler(admin_select_action)],
            SELECT_TYPE: [CallbackQueryHandler(admin_select_type)],
            SELECT_SUBJECT: [CallbackQueryHandler(admin_select_subject)],
            INPUT_YEAR_TYPE: [CallbackQueryHandler(admin_input_year_type)],
            INPUT_LEC_NUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_input_lecture)],
            DELETE_LEC_NUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_delete_lecture)],
            UPLOAD_FILE: [
                MessageHandler(
                    filters.AUDIO | filters.VOICE | filters.Document.ALL | filters.PHOTO, 
                    admin_receive_file
                ),
                CallbackQueryHandler(admin_cancel, pattern="^cancel_admin$")
            ]
        },
        fallbacks=[
            CommandHandler('cancel', admin_cancel),
            CallbackQueryHandler(admin_cancel, pattern="^cancel_admin$")
        ]
    )

    app.add_handler(admin_conv_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(student_callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_student_answer))

    print("🤖 Bot is running...")
    app.run_polling()
