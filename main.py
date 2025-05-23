import requests
import time
import threading
import schedule
from flask import Flask
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD, ADXIndicator
from binance.um_futures import UMFutures
import os

# Konstanten und Globals
MAX_CAPITAL = 150.0
bot_active = True
btc_strength_ok = True

app = Flask(__name__)
log_file = open("log.txt", "a", encoding="utf-8")

def log_print(msg):
    print(msg, flush=True)
    log_file.write(f"{msg}\n")
    log_file.flush()

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

def get_binance_client(chat_id):
    if str(chat_id) == os.getenv("CHAT_ID"):
        return UMFutures(key=os.getenv("BINANCE_API_KEY_1"), secret=os.getenv("BINANCE_API_SECRET_1"))
    elif str(chat_id) == os.getenv("CHAT_ID_2"):
        return UMFutures(key=os.getenv("BINANCE_API_KEY_2"), secret=os.getenv("BINANCE_API_SECRET_2"))
    return None

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
    if volume < avg_volume * 0.65:
        reasons.append("Volumen < 0.65× Durchschnitt")
    if adx < 10:
        reasons.append(f"ADX < 10 ({adx:.2f})")
    if rsi < 35 or rsi > 65:
        reasons.append(f"RSI außerhalb Bereich ({rsi:.2f})")
        return None, reasons

    if 35 <= rsi <= 47:
        if ema20 <= ema50:
            reasons.append("EMA20 nicht über EMA50")
            return None, reasons
        if macd_line <= macd_signal:
            reasons.append("MACD gegen LONG")
            return None, reasons
        direction = "LONG"
    elif 53 <= rsi <= 65:
        if ema20 >= ema50:
            reasons.append("EMA20 nicht unter EMA50")
            return None, reasons
        if macd_line >= macd_signal:
            reasons.append("MACD gegen SHORT")
            return None, reasons
        direction = "SHORT"
    else:
        reasons.append(f"RSI zu neutral ({rsi:.2f})")
        return None, reasons

    tp = price + 1.5 * atr if direction=="LONG" else price - 1.5*atr
    sl = price - 0.9 * atr if direction=="LONG" else price + 0.9*atr
    qty = round(MAX_CAPITAL / price, 3)

    msg = (f"📢 *Signal {direction} für {symbol}*\n"
           f"RSI: {rsi:.2f}, EMA: {ema20:.2f}/{ema50:.2f}, ADX: {adx:.2f}\n"
           f"TP: {tp:.4f} | SL: {sl:.4f}")
    return {"direction":direction,"qty":qty,"tp":tp,"sl":sl,"msg":msg}, None

def place_order(symbol, direction, quantity, tp, sl, chat_id):
    log_print(f"{symbol}: 🔑 Orderversuch mit API für Chat-ID {chat_id}")
    client = get_binance_client(chat_id)
    if client is None:
        log_print(f"{symbol}: Kein Client für {chat_id}")
        return
    side = "BUY" if direction=="LONG" else "SELL"
    position = direction
    if quantity < 0.001:
        log_print(f"{symbol}: ❌ Menge {quantity} zu klein")
        return
    for i in range(3):
        try:
            client.new_order(symbol=symbol, side=side,
                             positionSide=position, type="MARKET", quantity=quantity)
            log_print(f"{symbol}: ✅ Order gesetzt für {chat_id}")
            break
        except Exception as e:
            log_print(f"{symbol}: ❌ Order-Versuch {i+1} fehlgeschlagen: {e}")
            time.sleep(2)

def run_bot(chat_id):
    log_print(f"🚀 run_bot gestartet für Chat-ID {chat_id}")
    try:
        check_btc_strength()
        client = get_binance_client(chat_id)
        if not client:
            log_print(f"❌ Kein Binance-Client für {chat_id}")
            return
        info = client.exchange_info()
        symbols = [s['symbol'] for s in info['symbols']
                   if s['contractType']=="PERPETUAL" and s['quoteAsset']=="USDT" and s['status']=="TRADING"]
        log_print(f"✅ {len(symbols)} Symbole für {chat_id}")
        analyzed = signals = orders = 0
        for sym in symbols:
            try:
                log_print(f"{sym}: Analyse")
                res, reasons = analyze_symbol(sym)
                analyzed += 1
                if res is None:
                    continue
                send_telegram(res["msg"])
                signals +=1
                if bot_active:
                    place_order(sym, res["direction"], res["qty"], res["tp"], res["sl"], chat_id)
                    orders +=1
            except Exception as e:
                log_print(f"{sym}: Analyse-Fehler {e}")
        log_print(f"✅ {chat_id}: Analyzed {analyzed}, Signals {signals}, Orders {orders}")
    except Exception as e:
        log_print(f"{chat_id}: Lauf-Fehler {e}")

# Scheduler für beide Nutzer
schedule.every(5).minutes.do(lambda: threading.Thread(target=run_bot, args=(os.getenv("CHAT_ID"),)).start())
schedule.every(5).minutes.do(lambda: threading.Thread(target=run_bot, args=(os.getenv("CHAT_ID_2"),)).start())

def scheduler_loop():
    while True:
        schedule.run_pending()
        time.sleep(1)

@app.route("/")
def home():
    return "Bot läuft"

if __name__=="__main__":
    send_telegram("🚀 Multiuser Bot gestartet (2 Nutzer)")
    threading.Thread(target=run_bot, args=(os.getenv("CHAT_ID"),)).start()
    threading.Thread(target=run_bot, args=(os.getenv("CHAT_ID_2"),)).start()
    threading.Thread(target=scheduler_loop).start()
    app.run(host="0.0.0.0", port=8080)






