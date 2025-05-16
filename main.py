import requests
import time
import threading
from flask import Flask
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD, CCIIndicator, IchimokuIndicator
from ta.volatility import BollingerBands
import os
from datetime import datetime
from binance.um_futures import UMFutures

api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")
client = UMFutures(key=api_key, secret=api_secret)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

app = Flask(__name__)
log_file = open("log.txt", "a", encoding="utf-8")

def log_print(message):
    print(message, flush=True)
    log_file.write(f"{message}\n")
    log_file.flush()

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        response = requests.post(url, json=payload, timeout=5)
        if not response.ok:
            log_print(f"Telegram HTTP-Fehler {response.status_code}: {response.text}")
    except requests.exceptions.Timeout:
        log_print("Telegram-Timeout – Nachricht nicht gesendet.")
    except requests.exceptions.RequestException as e:
        log_print(f"Telegram-Request-Fehler: {e}")

def get_top_volume_symbols(limit=100):
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        response = requests.get(url, timeout=5)
        data = response.json()
        sorted_data = sorted(
            [s for s in data if s['symbol'].endswith('USDT')],
            key=lambda x: float(x['quoteVolume']),
            reverse=True
        )
        return [s['symbol'] for s in sorted_data[:limit]]
    except Exception as e:
        log_print(f"Fehler beim Laden der Volume-Daten: {e}")
        return []

def check_all_symbols():
    global market_sentiment
    market_sentiment = {"long": 0, "short": 0}

    symbols = get_top_volume_symbols(limit=100)
    if not symbols:
        log_print("Keine Symbole zum Prüfen verfügbar.")
        return

    for symbol in symbols:
        signal = analyze_combined(symbol)
        if signal:
            send_telegram(signal)
            log_print(f"{symbol}: Signal gesendet\n{signal}")
        else:
            log_print(f"{symbol}: Kein Signal")
        time.sleep(1)

    log_print(f"📊 Marktbreite: {market_sentiment['long']}x LONG | {market_sentiment['short']}x SHORT")

@app.route('/')
def home():
    return "Bot mit primärer 1m-Analyse läuft."

def run_bot():
    while True:
        check_all_symbols()
        time.sleep(600)

if __name__ == "__main__":
    send_telegram("🚀 Bot wurde mit Doppelanalyse gestartet.")
    log_print("Telegram-Startnachricht wurde gesendet.")
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=8080)
