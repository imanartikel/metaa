import sys
import os

# Tambahkan folder src ke python path agar import modul internal (seperti config)
# bisa berjalan dengan lancar saat dipanggil dari root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from main import main

if __name__ == "__main__":
    # Jika program dijalankan tanpa argumen (misalnya pada server production Railway),
    # secara default kita akan menjalankan Telegram bot.
    if len(sys.argv) == 1:
        sys.argv.append("telegram-bot")
    sys.exit(main())
