import os

# Bot tokeni (BotFather'dan olinadi)
BOT_TOKEN = os.getenv("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")

# Admin (o'qituvchi) telegram ID'lari, vergul bilan: "111111,222222"
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# Majburiy obuna bo'lish kerak bo'lgan kanal (username yoki -100... id)
CHANNEL_ID = os.getenv("CHANNEL_ID", "@your_channel_username")

DB_PATH = os.getenv("DB_PATH", "bot.db")
