import requests
import time
import threading
from flask import Flask
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator
from ta.volatility import AverageTrueRange
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
        df['open'] = pd.to_numeric(df['open'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])
        return df
    except Exception as e:
        print("Fehler beim Laden der Daten für", symbol, e)
        return None

def detect_trend(df):
    recent_highs = df['high'].iloc[-4:]
    recent_lows = df['low'].iloc[-4:]
    higher_highs = all(x < y for x, y in zip(recent_highs, recent_highs[1:]))
    lower_lows = all(x > y for x, y in zip(recent_lows, recent_lows[1:]))
    if higher_highs:
        return "up"
    elif lower_lows:
        return "down"
    else:
        return "sideways"

def calculate_tp_sl_atr(df, price):
    atr = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range().iloc[-1]
    tp = price + 2 * atr
    sl = price - 1 * atr
    return sl, tp

def analyze(df, symbol):
    try:
        rsi = RSIIndicator(close=df['close']).rsi().iloc[-1]
        macd_hist = MACD(close=df['close']).macd_diff().iloc[-1]
        ema = EMAIndicator(close=df['close'], window=20).ema_indicator().iloc[-1]
        price = df['close'].iloc[-1]
        vol_change = df['volume'].iloc[-1] / df['volume'].iloc[-2] if df['volume'].iloc[-2] > 0 else 1
        trend = detect_trend(df)
        sl, tp = calculate_tp_sl_atr(df, price)

        if 55 < rsi < 70 and macd_hist > 0 and price > ema and vol_change > 1.1 and trend == "up":
            return f"✅ {symbol}: LONG-SIGNAL\nRSI={rsi:.1f}, MACD>0, Preis > EMA20, Volumen +{vol_change:.1f}x, Trend: {trend}\n⬆⃣ TP: {tp:.4f} | ❌ SL: {sl:.4f}"
        elif rsi > 70 and macd_hist < 0 and price < ema and vol_change > 1.1 and trend == "down":
            sl_short, tp_short = tp, sl  # umdrehen für Shorts
            return f"❌ {symbol}: SHORT-SIGNAL\nRSI={rsi:.1f}, MACD<0, Preis < EMA20, Volumen +{vol_change:.1f}x, Trend: {trend}\n⬇⃣ TP: {tp_short:.4f} | ❌ SL: {sl_short:.4f}"
        else:
            return f"ℹ️ {symbol}: Kein Signal\nRSI={rsi:.1f}, MACD={macd_hist:.2f}, Preis={'>' if price > ema else '<'} EMA20, Volumen x{vol_change:.1f}, Trend: {trend}"
    except Exception as e:
        print("Analysefehler bei", symbol, e)
        return None

def check_all_symbols():
    symbols = [
        'LINKUSDT', 'ENAUSDT', 'MOVEUSDT', 'ONDOUSDT', 'XRPUSDT', 'ETHUSDT',
        'SOLUSDT', 'LTCUSDT', 'ADAUSDT', 'BTCUSDT', 'SUIUSDT', 'HBARUSDT', 'ALGOUSDT', 'XLMUSDT'
    ]
    for symbol in symbols:
        df = get_klines(symbol)
        if df is not None:
            signal = analyze(df, symbol)
            if signal:
                send_telegram(signal)
                print(signal)

def run_bot():
    while True:
        check_all_symbols()
        time.sleep(300)

if __name__ == "__main__":
    send_telegram("✅ Bot wurde gestartet und ist bereit.")
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=8080)

