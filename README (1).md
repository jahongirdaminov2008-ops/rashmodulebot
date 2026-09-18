# Matematika Milliy Sertifikat — Test Bot (Rasch modeli)

## 1. O'rnatish (lokal test uchun)

```bash
pip install -r requirements.txt
```

`config.py` dagi qiymatlarni to'ldiring (yoki muhit o'zgaruvchisi orqali bering):

```bash
export BOT_TOKEN="123456:ABC..."
export ADMIN_IDS="111111111,222222222"   # sizning telegram ID'ingiz(lar)
export CHANNEL_ID="@your_channel"
```

Telegram ID'ingizni bilish uchun @userinfobot ga yozing.

Ishga tushirish:

```bash
python bot.py
```

## 2. Ishlash tartibi

**Admin (o'qituvchi):**
1. `/newtest` — test ID, nomi, fayli (PDF/rasm), ochiq savollar soni, yopiq savollar sonini ketma-ket kiritadi.
2. `/addstudent` — `101 Aliyev Vali` formatida har bir o'quvchiga ID beradi (bu ID'ni o'quvchiga alohida yetkazasiz — masalan qog'ozda yoki shaxsiy xabarda).
3. O'quvchilar test topshirgach: `/exportanswers TEST1` — barcha javoblar excelga tushadi.
4. Siz excelni ochib, har bir savol uchun **to'g'ri bo'lsa 1, noto'g'ri bo'lsa 0** deb oxirgi ustunlarga yozasiz (`O1_ball`, `O2_ball`, ..., `Y1_ball`, ...).
5. To'ldirilgan faylni botga qaytarib yuklaysiz: `/importresults TEST1`, so'ng excelni yuborasiz.
6. Bot Rasch modeli (JMLE) bo'yicha har bir o'quvchining qobiliyatini hisoblab, ball/foiz/daraja jadvalini excel qilib qaytaradi va har bir o'quvchiga shaxsiy natijasini avtomatik yuboradi.

**O'quvchi:**
1. `/start` → kanalga obuna → admin bergan ID'ni yuboradi (bir marta ro'yxatdan o'tadi).
2. "🧪 Test topshirish" → test ID kiritadi → fayl keladi.
3. Avval ochiq javoblarni (`12.5|3/4|-7` formatida), keyin yopiq javoblarni (`1-A 2-B 3-C` formatida) yuboradi.
4. Natija o'qituvchi tekshirib, botga yuklaganidan keyin avtomatik keladi.

## 3. Muhim eslatma — Rasch modeli haqida

`rasch.py` dagi implementatsiya — bitta test doirasidagi natijalarni **guruh ichida** nisbiy baholaydi (JMLE, sodda Newton-Raphson iteratsiyasi). Rasmiy milliy sertifikat metodikasi esa **ankor (langar) savollar** orqali turli variant/imtihonlarni umumiy, doimiy shkalaga tenglashtiradi — bu ancha murakkab va markazlashgan statistik jarayon. Ya'ni bu bot amaliy mashq/ichki nazorat uchun juda mos, lekin rasmiy sertifikat hisob-kitobining aynan nusxasi emas.

## 4. Bulutga joylashtirish (Railway / Render misolida)

1. Loyihani GitHub'ga yuklang.
2. Railway.app yoki Render.com'da yangi "Worker"/"Background service" yarating, repo'ni ulang.
3. Start command: `python bot.py`
4. Environment Variables bo'limiga `BOT_TOKEN`, `ADMIN_IDS`, `CHANNEL_ID` ni qo'shing.
5. `bot.db` fayli konteyner qayta ishga tushganda o'chib ketmasligi uchun **persistent volume** (doimiy disk) ulang — aks holda o'quvchilar va natijalar yo'qolib qoladi.

## 5. Fayllar tuzilishi

```
math_test_bot/
├── bot.py            # asosiy handler'lar
├── database.py        # SQLite (students, tests, submissions, results)
├── rasch.py           # Rasch (JMLE) baholash moduli
├── excel_utils.py      # excel export/import
├── config.py           # sozlamalar
└── requirements.txt
```
