import requests
import time
import threading
import pandas as pd
from flask import Flask
from datetime import datetime
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD
from ta.volatility import AverageTrueRange
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
app = Flask(__name__)

@app.route("/")
def home():
    return "Trading Signal Bot läuft."

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("Fehler bei Telegram:", e)

def get_klines(symbol, interval="1h", limit=100):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
        ])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["volume"] = df["volume"].astype(float)
        return df
    except Exception as e:
        print(f"Fehler bei {symbol}:", e)
        return None

def analyze(df, symbol):
    rsi = RSIIndicator(df["close"]).rsi().iloc[-1]
    macd_diff = MACD(df["close"]).macd_diff().iloc[-1]
    ema = EMAIndicator(df["close"]).ema_indicator().iloc[-1]
    price = df["close"].iloc[-1]
    volume = df["volume"].iloc[-1]
    avg_volume = df["volume"].rolling(window=20).mean().iloc[-1]
    atr = AverageTrueRange(df["high"], df["low"], df["close"]).average_true_range().iloc[-1]

    signal = "NEUTRAL"
    reason = ""
    breakout = False
    if rsi < 35 and macd_diff > 0 and price > ema:
        signal = "LONG"
        reason = "RSI < 35, MACD > 0, Preis > EMA"
    elif rsi > 70 and macd_diff < 0 and price < ema:
        signal = "SHORT"
        reason = "RSI > 70, MACD < 0, Preis < EMA"

    if signal != "NEUTRAL":
        breakout = price > df["high"].iloc[-20:-1].max() if signal == "LONG" else price < df["low"].iloc[-20:-1].min()
        quality = "★★★" if breakout and volume > 1.5 * avg_volume else "★★" if volume > avg_volume else "★"
        icon = "✅" if signal == "LONG" else "❌"

        tp1 = price + 1.5 * atr if signal == "LONG" else price - 1.5 * atr
        tp2 = price + 2.5 * atr if signal == "LONG" else price - 2.5 * atr
        sl = price - 1.2 * atr if signal == "LONG" else price + 1.2 * atr

        message = (
            f"{icon} *{symbol}* Signal: *{signal}*
"
            f"_Grund:_ {reason} {'+ Breakout' if breakout else ''}
"
            f"📊 RSI: {rsi:.2f} | MACD: {macd_diff:.4f} | EMA: {ema:.2f}
"
            f"💰 Preis: {price:.4f} | Vol: {volume:.0f} vs Ø{avg_volume:.0f}
"
            f"🎯 TP1: {tp1:.4f} | TP2: {tp2:.4f} | SL: {sl:.4f}
"
            f"⭐️ Signalqualität: {quality}
"
            f"🕓 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )
        return message
    return None

def check_all_symbols():
    symbols = [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT", "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "TRXUSDT", "DOTUSDT",
        "MATICUSDT", "SHIBUSDT", "LTCUSDT", "LINKUSDT", "BCHUSDT", "ATOMUSDT", "XLMUSDT", "HBARUSDT", "INJUSDT", "APTUSDT",
        "PEPEUSDT", "FETUSDT", "RNDRUSDT", "TAOUSDT", "AAVEUSDT", "GRTUSDT", "ARBUSDT", "MKRUSDT", "JUPUSDT", "KASUSDT",
        "SUIUSDT", "OPUSDT", "FLRUSDT", "LDOUSDT", "IMXUSDT", "CFXUSDT", "DYDXUSDT", "TUSDT", "AGIXUSDT", "CHZUSDT",
        "DASHUSDT", "ZECUSDT", "ENSUSDT", "SANDUSDT", "MANAUSDT", "AXSUSDT", "1000SATSUSDT", "HYPEUSDT", "DEXEUSDT", "ZEREBROUSDT",
        "STMXUSDT", "WLDUSDT", "RDNTUSDT", "LQTYUSDT", "OCEANUSDT", "RLCUSDT", "TUSDT", "BICOUSDT", "IDUSDT", "PORTALUSDT",
        "ARKMUSDT", "TIAUSDT", "PYTHUSDT", "LINAUSDT", "HOOKUSDT", "BLURUSDT", "COTIUSDT", "KEYUSDT", "TRUUSDT", "MAGICUSDT",
        "ACHUSDT", "ALPHAUSDT", "JOEUSDT", "DARUSDT", "HIGHUSDT", "SUPERUSDT", "DEXTUSDT", "MASKUSDT", "SSVUSDT", "BANDUSDT",
        "DFIUSDT", "PHBUSDT", "BNTUSDT", "C98USDT", "DODOUSDT", "GALAUSDT", "WAVESUSDT", "SFPUSDT", "KAVAUSDT", "ILVUSDT"
    ]

    for symbol in symbols:
        df = get_klines(symbol)
        if df is not None:
            msg = analyze(df, symbol)
            if msg:
                send_telegram(msg)
                print(msg)
            else:
                print(f"{symbol}: Kein Signal.")

def run_bot():
    while True:
        check_all_symbols()
        time.sleep(300)

if __name__ == "__main__":
    send_telegram("📡 Bot wurde gestartet und läuft.")
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=8080)

