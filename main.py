import requests
import time
import threading
from flask import Flask
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

app = Flask(__name__)
test_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
test_payload = {'chat_id': CHAT_ID, 'text': 'Testnachricht vom Bot (Verbindung funktioniert!)'}
requests.post(test_url, json=test_payload)
@app.route('/')
def home():
    return "Multi-Coin Bot läuft."

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message}
    try:
        requests.post(url, json=payload)
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
    df['open'] = df['open'].astype(float)
    return df

def analyze(df, symbol):
    rsi = RSIIndicator(close=df['close'], window=14).rsi().iloc[-1]
    macd_diff = MACD(close=df['close']).macd_diff().iloc[-1]
    ema = EMAIndicator(close=df['close'], window=20).ema_indicator().iloc[-1]
    price = df['close'].iloc[-1]

    message = None

    if rsi < 30 and macd_diff > 0 and price > ema:
        message = f"{symbol}: LONG-SIGNAL (RSI={rsi:.2f}, MACD>0, Preis > EMA20)"
    elif rsi > 70 and macd_diff < 0 and price < ema:
        message = f"{symbol}: SHORT-SIGNAL (RSI={rsi:.2f}, MACD<0, Preis < EMA20)"

    return message

def check_all_symbols():
    symbols = ['LINKUSDT', 'ENAUSDT', 'MOVEUSDT', 'ONDOUSDT', 'XRPUSDT', 'ETHUSDT']
    for symbol in symbols:
        try:
            df = get_klines(symbol=symbol)
            signal = analyze(df, symbol)
            if signal:
                send_telegram(signal)
                print(signal)
            else:
                print(f"{symbol}: Kein Signal.")
        except Exception as e:
            print(f"Fehler bei {symbol}: {e}")

def run_bot():
    while True:
        check_all_symbols()
        time.sleep(300)
if __name__ == "__main__":
    send_telegram("Bot wurde gestartet und läuft.")
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=8080)

