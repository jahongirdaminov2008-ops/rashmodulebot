import asyncio
import logging
import os

from aiohttp import web
import numpy as np
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, FSInputFile,
)

import database as db
from rasch import estimate_rasch, theta_to_percent, daraja_from_percent
import excel_utils
from config import BOT_TOKEN, ADMIN_IDS, CHANNEL_ID

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

os.makedirs("exports", exist_ok=True)


# ---------------- FSM states ----------------

class Reg(StatesGroup):
    waiting_id = State()


class TestFlow(StatesGroup):
    waiting_test_id = State()
    waiting_open = State()
    waiting_closed = State()


class NewTest(StatesGroup):
    waiting_id = State()
    waiting_name = State()
    waiting_file = State()
    waiting_open_count = State()
    waiting_closed_count = State()


class AddStudent(StatesGroup):
    waiting_data = State()


class ImportResults(StatesGroup):
    waiting_test_id = State()
    waiting_file = State()


# ---------------- helpers ----------------

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        return False


def main_menu(user_id: int) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text="🧪 Test topshirish")]]
    if is_admin(user_id):
        rows.append([KeyboardButton(text="⚙️ Admin panel")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def sub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=f"https://t.me/{str(CHANNEL_ID).lstrip('@')}")],
        [InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")],
    ])


# ---------------- /start & registration ----------------

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    if not await is_subscribed(message.from_user.id):
        await message.answer(
            "Botdan foydalanish uchun avval kanalga obuna bo'ling, so'ng ✅ Tekshirish tugmasini bosing.",
            reply_markup=sub_keyboard(),
        )
        return

    student = db.get_student_by_telegram(message.from_user.id)
    if student:
        await message.answer(
            f"Xush kelibsiz, {student['full_name']}!",
            reply_markup=main_menu(message.from_user.id),
        )
        return

    if is_admin(message.from_user.id):
        await message.answer("Salom, admin!", reply_markup=main_menu(message.from_user.id))
        return

    await message.answer("Ro'yxatdan o'tish uchun sizga admin bergan ID raqamingizni yuboring:")
    await state.set_state(Reg.waiting_id)


@router.callback_query(F.data == "check_sub")
async def check_sub(callback, state: FSMContext):
    user_id = callback.from_user.id
    if not await is_subscribed(user_id):
        await callback.answer("Hali obuna bo'lmadingiz.", show_alert=True)
        return

    await callback.answer("Obuna tasdiqlandi ✅")
    student = db.get_student_by_telegram(user_id)
    if student:
        await callback.message.answer(f"Xush kelibsiz, {student['full_name']}!", reply_markup=main_menu(user_id))
    elif is_admin(user_id):
        await callback.message.answer("Salom, admin!", reply_markup=main_menu(user_id))
    else:
        await callback.message.answer("Ro'yxatdan o'tish uchun sizga admin bergan ID raqamingizni yuboring:")
        await state.set_state(Reg.waiting_id)


@router.message(Reg.waiting_id)
async def reg_id(message: Message, state: FSMContext):
    student_id = message.text.strip()
    ok = db.link_student(student_id, message.from_user.id)
    if not ok:
        await message.answer("Bu ID noto'g'ri yoki allaqachon band. Qaytadan yuboring, yoki adminga murojaat qiling.")
        return
    student = db.get_student_by_telegram(message.from_user.id)
    await state.clear()
    await message.answer(
        f"Ro'yxatdan muvaffaqiyatli o'tdingiz, {student['full_name']}!",
        reply_markup=main_menu(message.from_user.id),
    )


# ---------------- student: test topshirish ----------------

@router.message(F.text == "🧪 Test topshirish")
async def start_test(message: Message, state: FSMContext):
    student = db.get_student_by_telegram(message.from_user.id)
    if not student:
        await message.answer("Avval ro'yxatdan o'ting: /start")
        return
    await message.answer("Test ID raqamini kiriting:")
    await state.set_state(TestFlow.waiting_test_id)


@router.message(TestFlow.waiting_test_id)
async def got_test_id(message: Message, state: FSMContext):
    test_id = message.text.strip()
    test = db.get_test(test_id)
    if not test:
        await message.answer("Bunday test topilmadi. ID ni tekshirib, qaytadan yuboring.")
        return
    student = db.get_student_by_telegram(message.from_user.id)
    if db.has_submitted(test_id, student["student_id"]):
        await message.answer("Siz bu testni allaqachon topshirgansiz.")
        await state.clear()
        return

    await state.update_data(test_id=test_id)
    await message.answer_document(test["file_id"], caption=f"📄 {test['name']}")

    if test["open_count"] > 0:
        await message.answer(
            f"Ochiq savollar ({test['open_count']} ta) javoblarini quyidagi namunada yuboring:\n"
            f"`12.5|3/4|-7`  (har bir javob \"|\" belgisi bilan ajratilgan, {test['open_count']} ta qiymat)",
            parse_mode="Markdown",
        )
        await state.set_state(TestFlow.waiting_open)
    else:
        await state.update_data(open_answers="")
        await ask_closed(message, state, test)


@router.message(TestFlow.waiting_open)
async def got_open(message: Message, state: FSMContext):
    data = await state.get_data()
    test = db.get_test(data["test_id"])
    parts = [p.strip() for p in message.text.split("|")]
    if len(parts) != test["open_count"]:
        await message.answer(f"Xato: {test['open_count']} ta javob kutilmoqda, siz {len(parts)} ta yubordingiz. Qaytadan yuboring.")
        return
    await state.update_data(open_answers="|".join(parts))
    await ask_closed(message, state, test)


async def ask_closed(message: Message, state: FSMContext, test):
    if test["closed_count"] > 0:
        await message.answer(
            f"Yopiq (test) savollar ({test['closed_count']} ta) javoblarini quyidagi namunada yuboring:\n"
            f"`1-A 2-B 3-C 4-D`",
        )
        await state.set_state(TestFlow.waiting_closed)
    else:
        await finish_submission(message, state, closed_answers="")


@router.message(TestFlow.waiting_closed)
async def got_closed(message: Message, state: FSMContext):
    data = await state.get_data()
    test = db.get_test(data["test_id"])
    parts = message.text.split()
    if len(parts) != test["closed_count"]:
        await message.answer(f"Xato: {test['closed_count']} ta javob kutilmoqda ('1-A 2-B ...' shaklida). Qaytadan yuboring.")
        return
    await finish_submission(message, state, closed_answers="|".join(parts))


async def finish_submission(message: Message, state: FSMContext, closed_answers: str):
    data = await state.get_data()
    student = db.get_student_by_telegram(message.from_user.id)
    db.save_open_answers(data["test_id"], student["student_id"], data.get("open_answers", ""))
    if closed_answers:
        db.save_closed_answers(data["test_id"], student["student_id"], closed_answers)
    await state.clear()
    await message.answer(
        "✅ Test qabul qilindi. Javoblaringiz o'qituvchi tomonidan tekshiriladi, natijangiz e'lon qilinganda xabar beriladi.",
        reply_markup=main_menu(message.from_user.id),
    )


# ---------------- admin panel ----------------

@router.message(F.text == "⚙️ Admin panel")
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "Admin buyruqlari:\n"
        "/newtest — yangi test qo'shish\n"
        "/addstudent — o'quvchi ID qo'shish\n"
        "/students — o'quvchilar ro'yxati\n"
        "/exportanswers <test_id> — javoblarni excelga chiqarish\n"
        "/importresults <test_id> — baholangan excelni yuklab, Rasch bo'yicha hisoblash"
    )


@router.message(Command("newtest"))
async def newtest_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await message.answer("Test ID kiriting (masalan: TEST1):")
    await state.set_state(NewTest.waiting_id)


@router.message(NewTest.waiting_id)
async def newtest_id(message: Message, state: FSMContext):
    await state.update_data(test_id=message.text.strip())
    await message.answer("Test nomini kiriting:")
    await state.set_state(NewTest.waiting_name)


@router.message(NewTest.waiting_name)
async def newtest_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await message.answer("Test faylini yuboring (PDF/rasm/hujjat):")
    await state.set_state(NewTest.waiting_file)


@router.message(NewTest.waiting_file, F.document | F.photo)
async def newtest_file(message: Message, state: FSMContext):
    file_id = message.document.file_id if message.document else message.photo[-1].file_id
    await state.update_data(file_id=file_id)
    await message.answer("Ochiq savollar sonini kiriting (raqam):")
    await state.set_state(NewTest.waiting_open_count)


@router.message(NewTest.waiting_open_count)
async def newtest_open_count(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Raqam kiriting.")
        return
    await state.update_data(open_count=int(message.text))
    await message.answer("Yopiq savollar sonini kiriting (raqam):")
    await state.set_state(NewTest.waiting_closed_count)


@router.message(NewTest.waiting_closed_count)
async def newtest_closed_count(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Raqam kiriting.")
        return
    data = await state.get_data()
    db.add_test(data["test_id"], data["name"], data["file_id"], data["open_count"], int(message.text))
    await state.clear()
    await message.answer(f"✅ Test qo'shildi: {data['test_id']} ({data['name']})", reply_markup=main_menu(message.from_user.id))


@router.message(Command("addstudent"))
async def addstudent_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await message.answer("ID va F.I.Sh. ni shu formatda yuboring:\n`101 Aliyev Vali`", parse_mode="Markdown")
    await state.set_state(AddStudent.waiting_data)


@router.message(AddStudent.waiting_data)
async def addstudent_data(message: Message, state: FSMContext):
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Format xato. Masalan: `101 Aliyev Vali`", parse_mode="Markdown")
        return
    student_id, full_name = parts
    db.add_student(student_id, full_name)
    await state.clear()
    await message.answer(f"✅ O'quvchi qo'shildi: {student_id} — {full_name}", reply_markup=main_menu(message.from_user.id))


@router.message(Command("students"))
async def list_students(message: Message):
    if not is_admin(message.from_user.id):
        return
    rows = db.list_students()
    if not rows:
        await message.answer("O'quvchilar yo'q.")
        return
    lines = [f"{r['student_id']} — {r['full_name']} — {'✅ ro‘yxatdan o‘tgan' if r['telegram_id'] else '⏳ kutilmoqda'}" for r in rows]
    await message.answer("\n".join(lines))


@router.message(Command("exportanswers"))
async def export_answers(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("Foydalanish: /exportanswers TEST_ID")
        return
    test_id = command.args.strip()
    test = db.get_test(test_id)
    if not test:
        await message.answer("Bunday test topilmadi.")
        return
    submissions = db.list_submissions(test_id)
    if not submissions:
        await message.answer("Bu test bo'yicha hali javoblar yo'q.")
        return
    path = f"exports/{test_id}_javoblar.xlsx"
    excel_utils.export_submissions_to_excel(path, test_id, submissions, test["open_count"], test["closed_count"])
    await message.answer_document(FSInputFile(path), caption=f"{test_id} — javoblar ({len(submissions)} ta o'quvchi)")


@router.message(Command("importresults"))
async def import_results_start(message: Message, state: FSMContext, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("Foydalanish: /importresults TEST_ID (keyin baholangan excelni yuboring)")
        return
    test_id = command.args.strip()
    if not db.get_test(test_id):
        await message.answer("Bunday test topilmadi.")
        return
    await state.update_data(test_id=test_id)
    await message.answer("Baholangan (1/0 to'ldirilgan) excel faylini yuboring:")
    await state.set_state(ImportResults.waiting_file)


@router.message(ImportResults.waiting_file, F.document)
async def import_results_file(message: Message, state: FSMContext):
    data = await state.get_data()
    test_id = data["test_id"]
    test = db.get_test(test_id)

    local_path = f"exports/{test_id}_graded_input.xlsx"
    file = await bot.get_file(message.document.file_id)
    await bot.download_file(file.file_path, local_path)

    graded = excel_utils.read_graded_excel(local_path, test["open_count"], test["closed_count"])
    if not graded:
        await message.answer("Faylda ma'lumot topilmadi.")
        return

    student_ids = [r[0] for r in graded]
    full_names = [r[1] for r in graded]
    matrix = np.array([r[2] for r in graded], dtype=float)
    max_score = matrix.shape[1]

    theta, beta = estimate_rasch(matrix)
    percent = theta_to_percent(theta)

    results = []
    for i, sid in enumerate(student_ids):
        raw = int(matrix[i].sum())
        pct = float(percent[i])
        results.append({
            "student_id": sid,
            "full_name": full_names[i],
            "raw_score": raw,
            "max_score": max_score,
            "theta": float(theta[i]),
            "percent": pct,
            "daraja": daraja_from_percent(pct),
        })

    db.save_results(test_id, results)

    out_path = f"exports/{test_id}_natijalar.xlsx"
    excel_utils.build_results_excel(out_path, results)
    await state.clear()
    await message.answer_document(FSInputFile(out_path), caption=f"{test_id} — Rasch modeli bo'yicha natijalar")

    # har bir o'quvchiga shaxsiy natijasini yuborish
    students = {s["student_id"]: s for s in db.list_students()}
    for r in results:
        st = students.get(r["student_id"])
        if st and st["telegram_id"]:
            try:
                await bot.send_message(
                    st["telegram_id"],
                    f"📊 {test_id} natijangiz:\n"
                    f"To'g'ri javob: {r['raw_score']}/{r['max_score']}\n"
                    f"Foiz: {r['percent']:.1f}%\n"
                    f"Daraja: {r['daraja']}",
                )
            except Exception:
                pass


async def health(request):
    return web.Response(text="Bot ishlayapti ✅")


async def start_web_app():
    """Render bepul 'Web Service' tarifida port tinglashi shart bo'lgani uchun
    minimal HTTP server — tashqi pinger (UptimeRobot va h.k.) shu manzilga
    murojaat qilib, botni uyquga ketishdan saqlaydi."""
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Health-check server {port}-portda ishga tushdi")


async def main():
    db.init_db()
    await start_web_app()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
