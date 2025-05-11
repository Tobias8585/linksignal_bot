import requests
import time
import threading
from flask import Flask
import pandas as pd
from ta.momentum import RSIIndicator

import os
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

app = Flask(__name__)

@app.route('/')
def home():
    return "LINK Bot läuft."

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message}
    try:
        response = requests.post(url, json=payload)
        print("Telegram:", response.status_code, response.text)
    except Exception as e:
        print("Telegram-Fehler:", e)

def get_klines(symbol='LINKUSDT', interval='5m', limit=100):
    url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}'
    data = requests.get(url).json()
    df = pd.DataFrame(data, columns=[
        'time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'trades',
        'taker_buy_base', 'taker_buy_quote', 'ignore'
    ])
    df['close'] = df['close'].astype(float)
    return df

def check_signal():
    df = get_klines()
    rsi = RSIIndicator(close=df['close'], window=14).rsi()
    last_rsi = rsi.iloc[-1]
    print("Aktueller RSI:", last_rsi)

    if last_rsi < 30:
        send_telegram("RSI unter 30 – möglicher LONG-Einstieg bei LINKUSDT!")
    elif last_rsi > 70:
        send_telegram("RSI über 70 – möglicher SHORT-Einstieg bei LINKUSDT!")
    else:
        print("Kein Signal erkannt.")

def run_bot():
    while True:
        try:
            check_signal()
        except Exception as e:
            print("Fehler:", e)
        time.sleep(300)

if __name__ == "__main__":
    threading.Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': 8080}).start()
    send_telegram("Bot wurde gestartet und ist bereit.")
    run_bot()
