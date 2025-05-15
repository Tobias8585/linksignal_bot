# Vollintegrierte Version mit Doppelanalyse (1m + 5m)
import requests
import time
import threading
from flask import Flask
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
import os
from datetime import datetime

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
        requests.post(url, json=payload)
    except Exception as e:
        log_print("Telegram-Fehler: " + str(e))

def get_klines(symbol, interval="5m", limit=75):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=5)
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_asset_volume', 'number_of_trades',
                    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                ])
                df['close'] = df['close'].astype(float)
                df['volume'] = df['volume'].astype(float)
                df['high'] = df['high'].astype(float)
                df['low'] = df['low'].astype(float)
                return df
        except Exception as e:
            log_print(f"{symbol} {interval}: Fehler (Versuch {attempt + 1}/3): {e}")
        time.sleep(2)
    return None

def get_simple_signal(df):
    rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    ema = df['close'].ewm(span=20).mean().iloc[-1]
    ema50 = df['close'].ewm(span=50).mean().iloc[-1]
    macd_line = MACD(df['close']).macd().iloc[-1]
    price = df['close'].iloc[-1]

    long_signals = sum([rsi < 35, macd_line > 0, price > ema * 1.005 and price > ema50])
    short_signals = sum([rsi > 70, macd_line < 0, price < ema * 0.995 and price < ema50])

    if long_signals >= 2:
        return "LONG"
    elif short_signals >= 2:
        return "SHORT"
    return None

def analyze_combined(symbol):
    df_1m = get_klines(symbol, interval="1m", limit=50)
    df_5m = get_klines(symbol, interval="5m", limit=75)
    if df_1m is None or df_5m is None:
        return None

    signal_1m = get_simple_signal(df_1m)
    signal_5m = get_simple_signal(df_5m)
    if not signal_1m or not signal_5m or signal_1m != signal_5m:
        log_print(f"{symbol}: Kein doppeltes übereinstimmendes Signal")
        return None

    df = df_5m  # Hauptanalyse basiert auf 5m für alle weiteren Werte
    rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    ema = df['close'].ewm(span=20).mean().iloc[-1]
    ema50 = df['close'].ewm(span=50).mean().iloc[-1]
    macd = MACD(df['close'])
    macd_line = macd.macd().iloc[-1]
    macd_signal = macd.macd_signal().iloc[-1]
    macd_cross = macd_line > macd_signal if signal_5m == "LONG" else macd_line < macd_signal
    price = df['close'].iloc[-1]
    atr = (df['high'] - df['low']).rolling(window=14).mean().iloc[-1]
    volume = df['volume'].iloc[-1]
    avg_volume = df['volume'].rolling(window=20).mean().iloc[-1]

    if atr < price * 0.003:
        log_print(f"{symbol}: Kein Signal – ATR zu niedrig")
        return None

    breakout = (signal_5m == "LONG" and price > df['high'].iloc[-21:-1].max()) or \
               (signal_5m == "SHORT" and price < df['low'].iloc[-21:-1].min())
    strong_volume = volume > avg_volume * 1.3
    ema_cross = ema > ema50 if signal_5m == "LONG" else ema < ema50
    criteria_count = 3 + int(strong_volume) + int(breakout) + int(macd_cross) + int(ema_cross)

    if criteria_count >= 6:
        stars = "⭐⭐⭐"
        signal_strength = "🟢 Sehr starkes Signal"
    else:
        stars = "⭐⭐"
        signal_strength = "🟡 Gutes Signal"

    tp1 = price + 1.5 * atr if signal_5m == "LONG" else price - 1.5 * atr
    tp2 = price + 2.5 * atr if signal_5m == "LONG" else price - 2.5 * atr
    sl = price - 1.2 * atr if signal_5m == "LONG" else price + 1.2 * atr

    volatility_pct = atr / price * 100
    trend_text = "Seitwärts"
    if price > ema and price > ema50:
        trend_text = "Aufwärts"
    elif price < ema and price < ema50:
        trend_text = "Abwärts"

    rsi_zone = "neutral"
    if rsi < 30:
        rsi_zone = "überverkauft"
    elif rsi > 70:
        rsi_zone = "überkauft"

    macd_text = "MACD-Cross: ✅" if macd_cross else "MACD-Cross: ❌"
    breakout_text = "🚀 Breakout erkannt!" if breakout else ""

    msg = (
        f"🔔 *{symbol}* Doppelsignal: *{signal_5m}* {stars}\n"
        f"{signal_strength}\n"
        f"{breakout_text}\n"
        f"🧠 Bestätigt durch 1m + 5m\n"
        f"📈 Trend: {trend_text} | RSI-Zone: {rsi_zone} | Volatilität: {volatility_pct:.2f} %\n"
        f"{macd_text} | EMA-Cross: {'✅' if ema_cross else '❌'}\n"
        f"📊 RSI: {rsi:.2f} | MACD: {macd_line:.4f} | EMA20: {ema:.2f} | EMA50: {ema50:.2f}\n"
        f"🔥 Preis: {price:.4f} | Vol: {volume:.0f} vs Ø{avg_volume:.0f}\n"
        f"🎯 TP1: {tp1:.4f} | TP2: {tp2:.4f} | SL: {sl:.4f}\n"
        f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )

    return msg

def check_all_symbols():
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
    for symbol in symbols:
        signal = analyze_combined(symbol)
        if signal:
            send_telegram(signal)
            log_print(f"{symbol}: Signal gesendet\n{signal}")
        else:
            log_print(f"{symbol}: Kein übereinstimmendes Doppelsignal")
        time.sleep(1)

def run_bot():
    while True:
        check_all_symbols()
        time.sleep(600)

@app.route('/')
def home():
    return "Bot mit Doppelanalyse läuft."

if __name__ == "__main__":
    send_telegram("🚀 Bot wurde mit Doppelanalyse gestartet.")
    log_print("Telegram-Startnachricht wurde gesendet.")
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=8080)


