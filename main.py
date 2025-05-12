import requests
import time
import threading
import os
from flask import Flask
from datetime import datetime
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator
from ta.volatility import AverageTrueRange

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

app = Flask(__name__)

@app.route('/')
def home():
    return "Advanced Trading-Signal-Bot läuft."

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("Telegram Fehler:", e)

def get_klines(symbol):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1h&limit=100"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
        ])
        df['close'] = pd.to_numeric(df['close'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        df['volume'] = pd.to_numeric(df['volume'])
        return df
    except:
        return None

def analyze(df, symbol):
    if df is None or df.empty:
        return None

    price = df['close'].iloc[-1]
    rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    macd_line = MACD(df['close']).macd().iloc[-1]
    ema = EMAIndicator(df['close'], window=20).ema_indicator().iloc[-1]
    atr = AverageTrueRange(df['high'], df['low'], df['close'], window=14).average_true_range().iloc[-1]
    volume = df['volume'].iloc[-1]
    avg_volume = df['volume'].iloc[-6:-1].mean()

    signal = "NEUTRAL"
    reason = ""
    quality = "★"

    if rsi < 35 and price >= ema * 0.995:
        signal = "LONG"
        reason = "RSI < 35, Preis nahe EMA"
        quality = "★★" if macd_line > 0 else "★"
        if volume > 1.5 * avg_volume:
            quality = "★★★"
    elif rsi > 70 and price <= ema * 1.005:
        signal = "SHORT"
        reason = "RSI > 70, Preis nahe EMA"
        quality = "★★" if macd_line < 0 else "★"
        if volume > 1.5 * avg_volume:
            quality = "★★★"
    elif volume > 1.5 * avg_volume:
        signal = "BREAKOUT"
        reason = f"Volumenanstieg ({volume:.0f} > Ø{avg_volume:.0f})"
        quality = "★★"

    if signal == "NEUTRAL":
        return None

    tp1 = price + 1.5 * atr if signal == "LONG" else price - 1.5 * atr
    tp2 = price + 2.5 * atr if signal == "LONG" else price - 2.5 * atr
    sl = price - 1.2 * atr if signal == "LONG" else price + 1.2 * atr

    icon = "✅" if signal == "LONG" else "❌" if signal == "SHORT" else "⚡"
    msg = (
        f"{icon} *{symbol}* Signal: *{signal}*  
"
        f"Grund: {reason}  
"
        f"📊 RSI: {rsi:.2f} | MACD: {macd_line:.4f} | EMA: {ema:.2f}  
"
        f"💰 Preis: {price:.4f} | Vol: {volume:.0f} vs Ø{avg_volume:.0f}  
"
        f"🎯 TP1: {tp1:.4f} | TP2: {tp2:.4f} | SL: {sl:.4f}  
"
        f"⭐ Signalqualität: {quality}  
"
        f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )
    return msg

def check_all_symbols():
    symbols = [
        'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'SOLUSDT', 'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'TRXUSDT',
        'MATICUSDT', 'LTCUSDT', 'SHIBUSDT', 'LINKUSDT', 'ATOMUSDT', 'UNIUSDT', 'ALGOUSDT', 'HBARUSDT', 'VETUSDT', 'ICPUSDT',
        'FILUSDT', 'EGLDUSDT', 'NEARUSDT', 'SANDUSDT', 'THETAUSDT', 'MANAUSDT', 'XTZUSDT', 'RUNEUSDT', 'AAVEUSDT', 'GALAUSDT',
        'ENSUSDT', 'CHZUSDT', 'XLMUSDT', 'XMRUSDT', 'EOSUSDT', 'ARBUSDT', 'OPUSDT', 'TWTUSDT', 'LDOUSDT', 'CRVUSDT',
        'DYDXUSDT', 'ZILUSDT', 'CFXUSDT', 'MASKUSDT', '1INCHUSDT', 'SNXUSDT', 'KAVAUSDT', 'GMXUSDT', 'INJUSDT', 'RENUSDT',
        'IDUSDT', 'JOEUSDT', 'TURBOUSDT', 'STXUSDT', 'TIAUSDT', 'PYTHUSDT', 'SEIUSDT', 'WIFUSDT', 'PEPEUSDT', 'FETUSDT',
        'AGIXUSDT', 'KASUSDT', 'ZRXUSDT', 'RNDRUSDT', 'SXPUSDT', 'HOOKUSDT', 'JASMYUSDT', 'FLUXUSDT', 'ACHUSDT', 'DODOUSDT',
        'APTUSDT', 'SUIUSDT', 'COTIUSDT', 'HFTUSDT', 'DENTUSDT', 'STMXUSDT', 'WOOUSDT', 'GTCUSDT', 'HIGHUSDT', 'LITUSDT',
        'TVKUSDT', 'PORTOUSDT', 'FORTHUSDT', 'MOVRUSDT', 'BANDUSDT', 'FLOKIUSDT', 'UMAUSDT', 'OCEANUSDT', 'YGGUSDT', 'LOOMUSDT',
        'DEXEUSDT', 'XEMUSDT', 'SKLUSDT', 'MTLUSDT', 'CELRUSDT', 'BADGERUSDT', 'TRUUSDT', 'NKNUSDT', 'PHBUSDT', 'ALICEUSDT'
    ]
    for symbol in symbols:
        df = get_klines(symbol)
        message = analyze(df, symbol)
        if message:
            send_telegram(message)
            print(message)
        else:
            print(f"{symbol}: Kein Signal.")

def run_bot():
    while True:
        check_all_symbols()
        time.sleep(300)

if __name__ == "__main__":
    send_telegram("🤖 Trading-Signal-Bot wurde gestartet.")
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=8080)
