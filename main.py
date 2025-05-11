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

# Telegram Test-Nachricht beim Start
startup_message = "✅ Bot wurde gestartet und läuft."
url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
payload = {'chat_id': CHAT_ID, 'text': startup_message}
response = requests.post(url, json=payload)
print("Nachricht gesendet:", response.text)

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

def get_klines(symbol):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit=100"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time',
                                         'quote_asset_volume', 'number_of_trades', 'taker_buy_base_volume',
                                         'taker_buy_quote_volume', 'ignore'])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])
        return df
    except Exception as e:
        print("Fehler beim Laden der Daten für", symbol, e)
        return None

def analyze(df, symbol):
    try:
        rsi = RSIIndicator(close=df['close']).rsi().iloc[-1]
        macd_hist = MACD(close=df['close']).macd_diff().iloc[-1]
        ema = EMAIndicator(close=df['close'], window=20).ema_indicator().iloc[-1]
        price = df['close'].iloc[-1]
        vol_change = df['volume'].iloc[-1] / df['volume'].iloc[-2] if df['volume'].iloc[-2] > 0 else 1

        if 55 < rsi < 70 and macd_hist > 0 and price > ema and vol_change > 1.1:
            return f"✅ {symbol}: LONG-SIGNAL\nRSI={rsi:.1f}, MACD>0, Preis > EMA20, Volumen +{vol_change:.1f}x"
        elif rsi > 70 and macd_hist < 0 and price < ema and vol_change > 1.1:
            return f"❌ {symbol}: SHORT-SIGNAL\nRSI={rsi:.1f}, MACD<0, Preis < EMA20, Volumen +{vol_change:.1f}x"
        else:
            return None
    except Exception as e:
        print("Analysefehler bei", symbol, e)
        return None

def check_all_symbols():
    symbols = ['LINKUSDT', 'ENAUSDT', 'MOVEUSDT', 'ONDOUSDT', 'XRPUSDT', 'ETHUSDT']
    for symbol in symbols:
        df = get_klines(symbol)
        if df is not None:
            signal = analyze(df, symbol)
            if signal:
                send_telegram(signal)
                print(signal)
            else:
                print(f"{symbol}: Kein Signal.")

def run_bot():
    while True:
        check_all_symbols()
        time.sleep(300)

if __name__ == "__main__":
    send_telegram("✅ Bot wurde gestartet und ist bereit.")
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=8080)

