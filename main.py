from dotenv import load_dotenv
import os

# Direkt nach dem Import:
load_dotenv()

# Dann kommen alle anderen Importe:
import requests
import time
import threading
import schedule
from flask import Flask
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.trend import ADXIndicator
from binance.um_futures import UMFutures
from decimal import Decimal, ROUND_DOWN


def get_market_trend(client, symbols):
    import time

    def get_change(symbol, interval):
        try:
            klines = client.klines(symbol=symbol, interval=interval, limit=2)
            open_price = float(klines[0][1])
            close_price = float(klines[1][4])
            return ((close_price - open_price) / open_price) * 100
        except Exception as e:
            print(f"Fehler bei {symbol} ({interval}): {e}")
            return 0

    bullish = 0
    bearish = 0

    top_symbols = symbols[:30]  # nur die ersten 30 (sortiert nach Volumen vorher)

    for symbol in top_symbols:
        c5 = get_change(symbol, "5m")
        c15 = get_change(symbol, "15m")
        c1h = get_change(symbol, "1h")
        c24h = get_change(symbol, "1d")  # daily

        bullish_criteria = sum([
            c5 > 0.3,
            c15 > 0.5,
            c1h > 0.7,
            c24h > 1.0
        ])
        bearish_criteria = sum([
            c5 < -0.3,
            c15 < -0.5,
            c1h < -0.7,
            c24h < -1.0
        ])

        if bullish_criteria >= 2:
            bullish += 1
        elif bearish_criteria >= 2:
            bearish += 1

        time.sleep(0.1)  # API-Schutz pro Symbol

    # ✅ Rückgabe am Ende – nur einmal
    if bullish >= 25:
        return "strong_bullish"
    elif bearish >= 25:
        return "strong_bearish"
    elif bullish >= 20:
        return "bullish"
    elif bearish >= 20:
        return "bearish"
    else:
        return "neutral"




# Initialisiere den Binance-Client mit nur einem API-Zugang
client = UMFutures(key=os.getenv("BINANCE_API_KEY"), secret=os.getenv("BINANCE_API_SECRET"))

START_CAPITAL = 150.0
MAX_LOSS = 30.0
capital_lost = 0.0
bot_active = True


app = Flask(__name__)
log_file = open("log.txt", "a", encoding="utf-8")

def log_print(msg):
    print(msg, flush=True)
    log_file.write(f"{msg}\n")
    log_file.flush()

# ✅ HIER EINFÜGEN:
import csv
from datetime import datetime

def log_trade(symbol, direction, entry_price, qty, tp, sl, callback_rate):
    filename = "trades.csv"
    file_exists = os.path.isfile(filename)
    with open(filename, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "symbol", "direction", "entry_price", "qty", "tp", "sl", "callback_rate"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            symbol,
            direction,
            entry_price,
            qty,
            tp,
            sl,
            callback_rate
        ])


TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))

def send_telegram(message):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"},
            timeout=5
        )
    except Exception as e:
        log_print(f"Telegram-Fehler: {e}")

def get_klines(symbol, interval="5m", limit=100):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        res = requests.get(url, timeout=5)
        df = pd.DataFrame(res.json(), columns=['time','open','high','low','close','volume','x','y','z','a','b','c'])
        for c in ['open','high','low','close','volume']:
            df[c] = df[c].astype(float)
        return df
    except Exception as e:
        log_print(f"{symbol}: Fehler beim Laden: {e}")
        return None

def analyze_symbol(symbol):
    df = get_klines(symbol, limit=50)
    if df is None or len(df) < 20:
        return None, ["Unzureichende Daten"]

    rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    macd_line = MACD(df['close']).macd().iloc[-1]
    macd_signal = MACD(df['close']).macd_signal().iloc[-1]
    ema20 = EMAIndicator(df['close'], window=20).ema_indicator().iloc[-1]
    ema50 = EMAIndicator(df['close'], window=50).ema_indicator().iloc[-1]
    adx = ADXIndicator(df['high'], df['low'], df['close'], window=14).adx().iloc[-1]
    volume = df['volume'].iloc[-1]
    avg_volume = df['volume'].rolling(20).mean().iloc[-1]
    price = df['close'].iloc[-1]
    atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]

    reasons = []

    # Volumen-Check
    if volume < 0.5 * avg_volume:
        reasons.append(f"Volumen zu gering ({volume:.2f} < {avg_volume:.2f})")
        return None, reasons


    if rsi < 33 or rsi > 67:
        reasons.append(f"RSI außerhalb der Long-/Short-Bereiche ({rsi:.2f})")
        return None, reasons

    if 33 <= rsi <= 46:
        if ema20 <= ema50 * 0.995:
            reasons.append("EMA20 deutlich nicht über EMA50 (kein Aufwärtstrend)")
            return None, reasons
        if macd_line <= macd_signal:
            reasons.append("MACD gegen LONG")
            return None, reasons
        direction = "LONG"

    elif 54 <= rsi <= 67:
        if ema20 >= ema50 * 1.005:
            reasons.append("EMA20 deutlich nicht unter EMA50 (kein Abwärtstrend)")
            return None, reasons
        if macd_line >= macd_signal:
            reasons.append("MACD gegen SHORT")
            return None, reasons
        direction = "SHORT"


    else:
        reasons.append(f"RSI zu neutral für Long/Short ({rsi:.2f})")
        return None, reasons

    tp = price + 1.5 * atr if direction == "LONG" else price - 1.5 * atr
    sl = price - 0.9 * atr if direction == "LONG" else price + 0.9 * atr
    qty = round(START_CAPITAL / price, 3)

    msg = (f"📢 *Signal {direction} für {symbol}*\n"
            f"RSI: {rsi:.2f}, EMA: {ema20:.2f}/{ema50:.2f}\n"
            f"TP: {tp:.4f} | SL: {sl:.4f}")
    return {
        "direction": direction,
        "qty": qty,
        "tp": tp,
        "sl": sl,
        "msg": msg
    }, []



def round_to_step(value, step):
    """
    Rundet einen Wert sauber auf die zulässige Schrittgröße (Tickgröße oder Stückelung).
    Beispiel: 0.07631 bei Schritt 0.01 → 0.07
    """
    d_value = Decimal(str(value))
    d_step = Decimal(str(step))
    return float((d_value // d_step) * d_step)

    

def place_order(symbol, direction, quantity, tp, sl):
    log_print(f"{symbol}: Starte Orderversuch mit qty={quantity}, TP={tp}, SL={sl}")

    exchange_info = client.exchange_info()
    symbol_info = next(s for s in exchange_info['symbols'] if s['symbol'] == symbol)
    price_step = next(f for f in symbol_info['filters'] if f['filterType'] == 'PRICE_FILTER')['tickSize']
    qty_step = next(f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE')['stepSize']

    tp = round_to_step(tp, price_step)
    sl = round_to_step(sl, price_step)
    quantity = round_to_step(quantity, qty_step)

    side = "BUY" if direction == "LONG" else "SELL"
    position = "LONG" if direction == "LONG" else "SHORT"

    if quantity < 0.001:
        log_print(f"{symbol}: ❌ Ordermenge {quantity} zu klein – Order nicht gesendet")
        return

    potenzieller_verlust = 0.9 * abs(tp - sl) * quantity
    global capital_lost
    if capital_lost + potenzieller_verlust >= MAX_LOSS:
        log_print(f"{symbol}: ⚠️ Verlustgrenze erreicht – keine Order mehr erlaubt")
        send_telegram("⚠️ Maximaler Verlust erreicht – Bot gestoppt")
        return

    # ATR für dynamische Trailing-Logik berechnen
    df = get_klines(symbol, '5m', 100)
    df['ATR'] = talib.ATR(df['High'], df['Low'], df['Close'], timeperiod=14)
    last_atr = df['ATR'].iloc[-1] if 'ATR' in df and not df['ATR'].isna().all() else 0.0

    # Dynamische Trailing-Werte setzen
    if last_atr < 0.005:
        callback_rate = 0.35
        activation_multiplier = 1.007
    elif last_atr < 0.015:
        callback_rate = 0.75
        activation_multiplier = 1.01
    else:
        callback_rate = 1.2
        activation_multiplier = 1.015

    for attempt in range(3):
        try:
            order = client.new_order(
                symbol=symbol,
                side=side,
                positionSide=position,
                type="MARKET",
                quantity=quantity
            )

            # Einstiegspreis aus tatsächlicher Order verwenden
            price = float(order['fills'][0]['price'])

            capital_lost += potenzieller_verlust
            log_print(f"{symbol}: ✅ Order {side} {quantity} erfolgreich")
            log_print(f"{symbol}: 📉 Kumulierter Verlust: {capital_lost:.2f} USDT")

            log_trade(symbol, direction, price, quantity, tp, sl, callback_rate)


            sl_order_type = "STOP_MARKET"
            sl_side = "SELL" if direction == "LONG" else "BUY"
            position_side = "LONG" if direction == "LONG" else "SHORT"

            # ✅ Dynamischer Trailing TP
            try:
                activation_price = round(price * activation_multiplier, 4) if direction == "LONG" else round(price / activation_multiplier, 4)
                client.new_order(
                    symbol=symbol,
                    side=sl_side,
                    positionSide=position_side,
                    type="TRAILING_STOP_MARKET",
                    activationPrice=activation_price,
                    callbackRate=callback_rate,
                    reduceOnly=True
                )
                log_print(f"{symbol}: ✅ Trailing TP gesetzt – Aktivierung bei {activation_price}, callback {callback_rate}%")
            except Exception as e:
                log_print(f"{symbol}: ❌ Fehler beim Setzen des Trailing TP: {e}")

            # Fester SL
            try:
                client.new_order(
                    symbol=symbol,
                    side=sl_side,
                    positionSide=position_side,
                    type=sl_order_type,
                    stopPrice=round(sl, 4),
                    closePosition=True,
                    timeInForce="GTC"
                )
                log_print(f"{symbol}: ✅ SL gesetzt bei {sl:.4f}")
            except Exception as e:
                log_print(f"{symbol}: ❌ Fehler beim Setzen des SL: {e}")

            break

        except Exception as e:
            log_print(f"{symbol}: ❌ Order-Versuch {attempt + 1} fehlgeschlagen: {e}")
            time.sleep(2)


def run_bot():
    log_print("\U0001F680 run_bot gestartet")
    log_print("\U0001F4CA Starte neue Analyse...")
    try:
        info = client.exchange_info()
        symbols = [s['symbol'] for s in info['symbols']
                   if s['contractType'] == "PERPETUAL" and s['quoteAsset'] == "USDT" and s['status'] == "TRADING"]
        log_print(f"✅ {len(symbols)} Symbole geladen")

        # ⭐ NEU: Markttrend bestimmen
        market_trend = get_market_trend(client, symbols)
        log_print(f"⬆️ Markttrend erkannt: {market_trend.upper()}")

        analyzed = signals = orders = 0

        for sym in symbols:
            try:
                log_print(f"{sym}: Analyse")
                res, reasons = analyze_symbol(sym)
                analyzed += 1

                if res is None:
                    log_print(f"{sym}: ❌ Kein gültiges Signal – Gründe: {', '.join(reasons)}")
                    continue

                # ❗ Nur bei extremem Gegentrend blockieren
                if res["direction"] == "LONG" and market_trend == "strong_bearish":
                    log_print(f"{sym}: ❌ Long blockiert durch starken Bärenmarkt")
                    continue
                if res["direction"] == "SHORT" and market_trend == "strong_bullish":
                    log_print(f"{sym}: ❌ Short blockiert durch starken Bullenmarkt")
                    continue


                send_telegram(res["msg"])
                signals += 1

                if bot_active:
                    log_print(f"{sym}: ✅ Signal gültig – starte Order...")
                    place_order(sym, res["direction"], res["qty"], res["tp"], res["sl"])
                    orders += 1
                else:
                    log_print(f"{sym}: 🔒 Bot nicht aktiv – keine Order trotz gültigem Signal.")
            except Exception as e:
                log_print(f"{sym}: Analyse-Fehler {e}")

        log_print(f"✅ Analyse abgeschlossen: {analyzed} geprüft, {signals} Signale, {orders} Orders")

    except Exception as e:
        log_print(f"❌ Lauf-Fehler: {e}")


def scheduler_loop():
    while True:
        schedule.run_pending()
        time.sleep(1)

@app.route("/")
def home():
    return "Bot läuft"
    
import socket

def is_port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("0.0.0.0", port)) != 0
        
if __name__ == "__main__":
    send_telegram("🚀 Bot gestartet")

    # 1. Starte Bot direkt einmal
    run_bot()

    # 2. Starte Scheduler
    schedule.every(1).minutes.do(run_bot)
    threading.Thread(target=scheduler_loop, daemon=True).start()

    # 3. Starte Flask nur, wenn Port 8080 frei ist
    if is_port_free(8080):
        threading.Thread(target=lambda: app.run(host="0.0.0.0", port=8080), daemon=True).start()
    else:
        print("⚠️ Flask-Start übersprungen: Port 8080 ist belegt.")

    # 4. Endlosschleife
    while True:
        time.sleep(60)






