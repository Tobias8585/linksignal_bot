import requests
import time
import threading
import schedule
from flask import Flask, request
from bs4 import BeautifulSoup
import pytz
from pytz import timezone
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD, CCIIndicator, ADXIndicator
from datetime import datetime, timedelta
from binance.um_futures import UMFutures
import os

# Konstante Limits
MAX_CAPITAL = 150.0
MAX_DRAWDOWN = 30.0

# Initiale Statuswerte
current_profit = 0.0
bot_active = True
btc_strength_ok = True

app = Flask(__name__)
log_file = open("log.txt", "a", encoding="utf-8")

def log_print(msg):
    print(msg, flush=True)
    log_file.write(f"{msg}\n")
    log_file.flush()

# Telegram-Versand
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_IDS = [os.getenv("CHAT_ID"), os.getenv("CHAT_ID_2")]

def send_telegram(message):
    for chat_id in set(CHAT_IDS):
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
                timeout=5
            )
        except Exception as e:
            log_print(f"Telegram-Fehler: {e}")

# Binance Client
def get_binance_client(chat_id):
    if str(chat_id) == os.getenv("CHAT_ID"):
        return UMFutures(key=os.getenv("BINANCE_API_KEY_1"), secret=os.getenv("BINANCE_API_SECRET_1"))
    elif str(chat_id) == os.getenv("CHAT_ID_2"):
        return UMFutures(key=os.getenv("BINANCE_API_KEY_2"), secret=os.getenv("BINANCE_API_SECRET_2"))
    return None

# BTC-Stärke (Infozweck)
def check_btc_strength():
    global btc_strength_ok
    df = get_klines("BTCUSDT", "5m", 50)
    if df is None:
        btc_strength_ok = True
        return
    rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    macd = MACD(df['close']).macd().iloc[-1]
    ema20 = df['close'].ewm(span=20).mean().iloc[-1]
    ema50 = df['close'].ewm(span=50).mean().iloc[-1]
    price = df['close'].iloc[-1]
    btc_strength_ok = (rsi > 50 and macd > 0 and price > ema20 and price > ema50)

# Klines laden
def get_klines(symbol, interval="5m", limit=100):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        res = requests.get(url, timeout=5)
        data = res.json()
        df = pd.DataFrame(data, columns=['time','open','high','low','close','volume','x','y','z','a','b','c'])
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        return df
    except Exception as e:
        log_print(f"{symbol}: Fehler beim Laden: {e}")
        return None

# Hauptanalyse
def analyze_symbol(symbol):
    df = get_klines(symbol, limit=50)
    if df is None or len(df) < 20:
        return

    rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    macd = MACD(df['close'])
    macd_line = macd.macd().iloc[-1]
    macd_signal = macd.macd_signal().iloc[-1]
    ema20 = EMAIndicator(df['close'], window=20).ema_indicator().iloc[-1]
    ema50 = EMAIndicator(df['close'], window=50).ema_indicator().iloc[-1]
    adx = ADXIndicator(df['high'], df['low'], df['close'], window=14).adx().iloc[-1]
    volume = df['volume'].iloc[-1]
    avg_volume = df['volume'].rolling(20).mean().iloc[-1]
    price = df['close'].iloc[-1]
    atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]

    reasons = []

    if volume < avg_volume * 0.65:
        reasons.append("Volumen < 0.65× Durchschnitt")
    if adx < 10:
        reasons.append(f"ADX < 10 ({adx:.2f})")
    if not (rsi < 40 or rsi > 60):
        reasons.append(f"RSI neutral ({rsi:.2f})")

    if rsi < 40:
        if not (ema20 > ema50):
            reasons.append("EMA20 nicht über EMA50 (kein Aufwärtstrend)")
            return None, reasons  # HARTE Abweisung
        if not (macd_line > macd_signal):
            reasons.append("MACD gegen LONG")
            return None, reasons  # HARTE Abweisung

    elif rsi > 60:
        if not (ema20 < ema50):
            reasons.append("EMA20 nicht unter EMA50 (kein Abwärtstrend)")
            return None, reasons  # HARTE Abweisung
        if not (macd_line < macd_signal):
            reasons.append("MACD gegen SHORT")
            return None, reasons  # HARTE Abweisung


    if reasons:
        log_print(f"{symbol}: ❌ Kein Trade – Gründe: {', '.join(reasons)}")
        return

    direction = "LONG" if rsi < 40 else "SHORT"
    tp = price + 1.5 * atr if direction == "LONG" else price - 1.5 * atr
    sl = price - 0.9 * atr if direction == "LONG" else price + 0.9 * atr
    qty = round(MAX_CAPITAL / price, 3)

    msg = (
    f"📢 *Signal {direction} für {symbol}*\n"
    f"RSI: {rsi:.2f}, MACD: {macd_line - macd_signal:.4f}, EMA: {ema20:.4f}/{ema50:.4f}, ADX: {adx:.2f}\n"
    f"TP: {tp:.4f} | SL: {sl:.4f}"
)

    send_telegram(msg)

    if bot_active:
        place_order(symbol, direction, qty, tp, sl)

# Order platzieren
def place_order(symbol, direction, quantity, tp, sl):
    client = get_binance_client(os.getenv("CHAT_ID"))
    if client is None:
        log_print(f"{symbol}: Kein Client")
        return
    try:
        side = "BUY" if direction == "LONG" else "SELL"
        position = "LONG" if direction == "LONG" else "SHORT"
        client.new_order(symbol=symbol, side=side, positionSide=position, type="MARKET", quantity=quantity)
        log_print(f"{symbol}: Order {side} {quantity} gesetzt")
    except Exception as e:
        log_print(f"{symbol}: Fehler bei Order: {e}")

def run_bot():
    check_btc_strength()
    client = get_binance_client(os.getenv("CHAT_ID"))
    if not client:
        return
    try:
        info = client.exchange_info()
        symbols = [
            s['symbol'] for s in info['symbols']
            if s['contractType'] == 'PERPETUAL'
            and s['quoteAsset'] == 'USDT'
            and s['status'] == 'TRADING'
        ]
        log_print(f"✅ Symbole geladen: {len(symbols)} Futures-Paare")
        if not symbols:
            log_print("⚠️ Keine Symbole gefunden – Prüfe exchange_info()")
            return
    except Exception as e:
        log_print(f"Fehler bei exchange_info: {e}")
        return

    for symbol in symbols:
        analyze_symbol(symbol)
        time.sleep(0.05)  # vorher 0.5 → jetzt 10× schneller


# Bot alle 5 Minuten ausführen
schedule.every(5).minutes.do(run_bot)

def scheduler_loop():
    while True:
        schedule.run_pending()
        time.sleep(1)


# Flask Start
@app.route('/')
def home():
    return "Bot läuft"

if __name__ == '__main__':
    send_telegram("🚀 Vereinfachter Bot gestartet")
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=8080)





