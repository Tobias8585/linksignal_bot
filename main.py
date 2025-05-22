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
bot_active = True


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

def analyze_symbol(symbol):
    df = get_klines(symbol, limit=50)
    if df is None or len(df) < 20:
        return None, ["Unzureichende Daten"]

    # Berechnungen
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

    # Filtergründe
    if volume < avg_volume * 0.65:
        reasons.append("Volumen < 0.65× Durchschnitt")
    if adx < 10:
        reasons.append(f"ADX < 10 ({adx:.2f})")
    if rsi < 35 or rsi > 65:
        reasons.append(f"RSI außerhalb der Long-/Short-Bereiche ({rsi:.2f})")
        return None, reasons

    # Richtung bestimmen
    if 35 <= rsi <= 47:
        if not (ema20 > ema50):
            reasons.append("EMA20 nicht über EMA50 (kein Aufwärtstrend)")
            return None, reasons
        if not (macd_line > macd_signal):
            reasons.append("MACD gegen LONG")
            return None, reasons
        direction = "LONG"

    elif 53 <= rsi <= 65:
        if not (ema20 < ema50):
            reasons.append("EMA20 nicht unter EMA50 (kein Abwärtstrend)")
            return None, reasons
        if not (macd_line < macd_signal):
            reasons.append("MACD gegen SHORT")
            return None, reasons
        direction = "SHORT"

    else:
        reasons.append(f"RSI zu neutral für Long/Short ({rsi:.2f})")
        return None, reasons

    # Falls trotzdem Gründe existieren (zusätzlicher Schutz)
    if reasons:
        return None, reasons

    # Erfolgsfall: Trade vorbereiten
    tp = price + 1.5 * atr if direction == "LONG" else price - 1.5 * atr
    sl = price - 0.9 * atr if direction == "LONG" else price + 0.9 * atr
    qty = round(MAX_CAPITAL / price, 3)

    msg = (
        f"📢 *Signal {direction} für {symbol}*\n"
        f"RSI: {rsi:.2f}, MACD: {macd_line - macd_signal:.4f}, "
        f"EMA: {ema20:.4f}/{ema50:.4f}, ADX: {adx:.2f}\n"
        f"TP: {tp:.4f} | SL: {sl:.4f}"
    )

    return {
        "direction": direction,
        "price": price,
        "tp": tp,
        "sl": sl,
        "qty": qty,
        "msg": msg
    }, None


# Order platzieren
def place_order(symbol, direction, quantity, tp, sl):
    log_print(f"{symbol}: Starte Orderversuch mit qty={quantity}, TP={tp}, SL={sl}")

    client = get_binance_client(os.getenv("CHAT_ID"))
    if client is None:
        log_print(f"{symbol}: Kein Client")
        return

    side = "BUY" if direction == "LONG" else "SELL"
    position = "LONG" if direction == "LONG" else "SHORT"

    if quantity < 0.001:
        log_print(f"{symbol}: ❌ Ordermenge {quantity} zu klein – Order nicht gesendet")
        return

    for attempt in range(3):
        try:
            client.new_order(
                symbol=symbol,
                side=side,
                positionSide=position,
                type="MARKET",
                quantity=quantity
            )
            log_print(f"{symbol}: ✅ Order {side} {quantity} gesetzt")
            break  # Wenn erfolgreich, Schleife verlassen
        except Exception as e:
            log_print(f"{symbol}: ❌ Order-Versuch {attempt + 1} fehlgeschlagen: {e}")
            time.sleep(2)

def run_bot():
    log_print("🚀 run_bot() gestartet – Anfang der Funktion erreicht")
    try:
        log_print("🚦 Starte neuen run_bot() Durchlauf")

        check_btc_strength()
        client = get_binance_client(os.getenv("CHAT_ID"))
        if not client:
            log_print("❌ Kein Binance-Client verfügbar")
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
            log_print(f"🔍 Beginne Analyse von {len(symbols)} Symbolen")

            if not symbols:
                log_print("⚠️ Keine Symbole gefunden – Prüfe exchange_info()")
                return
        except Exception as e:
            log_print(f"❌ Fehler bei exchange_info: {e}")
            return

        for symbol in symbols:
            try:
                log_print(f"{symbol}: 🧠 Analyse gestartet")
                result, reasons = analyze_symbol(symbol)

                if result is None:
                    log_print(f"{symbol}: ❌ Kein Trade – Gründe: {', '.join(reasons)}")
                    continue

                log_print(f"{symbol}: ✅ Signal erkannt → {result['direction']}")
                send_telegram(result["msg"])

                if bot_active:
                    log_print(f"{symbol}: 🔄 place_order() wird jetzt ausgeführt mit qty={result['qty']}, TP={result['tp']}, SL={result['sl']}")
                    place_order(symbol, result["direction"], result["qty"], result["tp"], result["sl"])

            except Exception as e:
                log_print(f"{symbol}: ⚠️ Fehler bei Analyse: {e}")

    # Debug-Zusammenfassung
    log_print(f"🧠 Debug-Zähler: Analysiert: {analyzed}, Signale: {signals_found}, Orders: {orders_placed}")

except Exception as outer_error:
    log_print(f"❌ Fehler im run_bot(): {outer_error}")


# Bot alle 5 Minuten ausführen
schedule.every(5).minutes.do(lambda: threading.Thread(target=run_bot).start())

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
    threading.Thread(target=run_bot).start()  # 🔁 run_bot sofort beim Start!
    threading.Thread(target=scheduler_loop).start()
    app.run(host='0.0.0.0', port=8080)





