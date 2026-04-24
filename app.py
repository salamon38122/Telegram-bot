from flask import Flask
import threading
import os
from media_bot import main as bot_main

app = Flask(__name__)

@app.route('/')
def health():
    return "Bot is running!", 200

def run_bot():
    # لا حاجة لإنشاء حلقة يدوياً، bot_main يديرها بنفسه
    bot_main()

if __name__ == "__main__":
    thread = threading.Thread(target=run_bot)
    thread.daemon = True   # يغلق الخيط عند إيقاف العملية الرئيسية
    thread.start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
