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
    urls = [
        f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}",
        f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    ]
    sources = ["Futures", "Spot"]
    for url, source in zip(urls, sources):
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
                    log_print(f"{symbol}: Daten erfolgreich geladen von {source}")
                    return df
                else:
                    log_print(f"{symbol}: {source} – Leere Datenantwort (Versuch {attempt + 1}/3)")
            except Exception as e:
                log_print(f"{symbol}: {source} – Fehler (Versuch {attempt + 1}/3): {e}")
            time.sleep(2)
    return None

def analyze(df, symbol):
    required_columns = ['close', 'high', 'low', 'volume']
    for col in required_columns:
        if col not in df.columns:
            log_print(f"{symbol}: Analyse übersprungen – fehlende Spalte: {col}")
            return None

    rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    ema = df['close'].ewm(span=20).mean().iloc[-1]
    ema50 = df['close'].ewm(span=50).mean().iloc[-1]
    macd_line = MACD(df['close']).macd().iloc[-1]
    price = df['close'].iloc[-1]
    atr = (df['high'] - df['low']).rolling(window=14).mean().iloc[-1]
    volume = df['volume'].iloc[-1]
    avg_volume = df['volume'].rolling(window=20).mean().iloc[-1]

    long_signals = sum([rsi < 35, macd_line > 0, price > ema * 1.005 and price > ema50])
    short_signals = sum([rsi > 70, macd_line < 0, price < ema * 0.995 and price < ema50])

    log_print(
        f"{symbol}: Long-Signals={long_signals}, Short-Signals={short_signals}, "
        f"RSI={rsi:.2f}, MACD={macd_line:.4f}, Preis={price:.4f}, EMA20={ema:.4f}, EMA50={ema50:.4f}"
    )

    signal = "NEUTRAL"
    reason = ""

    if long_signals == 3:
        signal = "LONG"
        reason = "Alle 3 Long-Kriterien erfüllt"
    elif short_signals == 3:
        signal = "SHORT"
        reason = "Alle 3 Short-Kriterien erfüllt"
    else:
        log_print(f"{symbol}: Kein Signal - Grund: Weniger als 3 Kriterien erfüllt")
        return None

    criteria_count = 3
    if volume > avg_volume * 1.3:
        criteria_count += 1

    high_last_20 = df['high'].iloc[-21:-1].max()
    low_last_20 = df['low'].iloc[-21:-1].min()
    is_breakout = (signal == "LONG" and price > high_last_20) or \
                  (signal == "SHORT" and price < low_last_20)

    breakout_text = "🚀 Breakout erkannt!" if is_breakout else ""
    if is_breakout:
        criteria_count += 1

    if criteria_count >= 5:
        stars = "⭐⭐⭐"
        signal_strength = "🟢 Sehr starkes Signal"
    elif criteria_count == 4:
        stars = "⭐⭐"
        signal_strength = "🟡 Gutes Signal"
    else:
        stars = "⭐"
        signal_strength = "🟠 Schwaches Signal"

    tp1 = price + 1.5 * atr if signal == "LONG" else price - 1.5 * atr
    tp2 = price + 2.5 * atr if signal == "LONG" else price - 2.5 * atr
    sl = price - 1.2 * atr if signal == "LONG" else price + 1.2 * atr

    msg = (
        f"🔔 *{symbol}* Signal: *{signal}* {stars}\n"
        f"{signal_strength}\n"
        f"{breakout_text}\n"
        f"🧠 Grund: {reason}\n"
        f"📊 RSI: {rsi:.2f} | MACD: {macd_line:.4f} | EMA20: {ema:.2f} | EMA50: {ema50:.2f}\n"
        f"🔥 Preis: {price:.4f} | Vol: {volume:.0f} vs Ø{avg_volume:.0f}\n"
        f"🎯 TP1: {tp1:.4f} | TP2: {tp2:.4f} | SL: {sl:.4f}\n"
        f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )

    log_print(
        f"{symbol}: SIGNAL={signal} | Grund={reason} | Sterne={stars} | Signalstärke={signal_strength} | "
        f"Breakout={is_breakout} | RSI={rsi:.2f}, MACD={macd_line:.4f}, Preis={price:.4f}, EMA20={ema:.4f}, EMA50={ema50:.4f}, "
        f"Vol={volume:.0f}/Ø{avg_volume:.0f}, TP1={tp1:.4f}, TP2={tp2:.4f}, SL={sl:.4f}"
    )

    return msg

def check_all_symbols():
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]  # TEMPORÄR GEKÜRZT

    total = len(symbols)
    skipped = 0
    signals = 0
    nodata = 0

    for symbol in symbols:
        df = get_klines(symbol)

        if df is None or len(df) == 0:
            log_print(f"{symbol}: Erster Datenversuch fehlgeschlagen – versuche erneut in 2 Sekunden")
            time.sleep(2)
            df = get_klines(symbol)

        if df is not None:
            signal = analyze(df, symbol)
            if signal:
                send_telegram(signal)
                signals += 1
                log_print(f"Telegram gesendet: {symbol}\nInhalt: {signal}")
            else:
                skipped += 1
        else:
            nodata += 1
            log_print(f"{symbol}: Keine Daten vom Server")

        time.sleep(0.5)

    log_print("\n--- Zusammenfassung ---")
    log_print(f"Gesamt: {total} | Signale: {signals} | Übersprungen: {skipped} | Keine Daten: {nodata}\n")

    if signals == 0:
        send_telegram("🧘 Kein Signal bei allen geprüften Coins – Markt aktuell ruhig.")

def run_bot():
    while True:
        check_all_symbols()
        time.sleep(600)

@app.route('/')
def home():
    return "Bot läuft und empfängt Anfragen."

if __name__ == "__main__":
    send_telegram("🚀 Bot wurde gestartet und überwacht Coins mit gelockerten Bedingungen.")
    log_print("Telegram-Startnachricht wurde gesendet.")
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=8080)

