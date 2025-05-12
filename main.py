import requests
import time
import threading
import os
from flask import Flask
from datetime import datetime
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

app = Flask(__name__)

@app.route('/')
def home():
    return "Optimierter Trading-Bot läuft."

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("Telegram-Fehler:", e)

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
        df['volume'] = pd.to_numeric(df['volume'])
        return df
    except Exception as e:
        print(f"Fehler beim Abrufen von {symbol}: {e}")
        return None

def analyze(df, symbol):
    if df is None or df.empty:
        return None

    rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    macd_line = MACD(df['close']).macd().iloc[-1]
    ema = EMAIndicator(df['close'], window=20).ema_indicator().iloc[-1]
    price = df['close'].iloc[-1]
    volume = df['volume'].iloc[-1]
    avg_volume = df['volume'].iloc[-6:-1].mean()

    signal = "NEUTRAL"
    reason = ""

    if rsi < 35 and price >= ema * 0.995:
        signal = "LONG"
        reason = "RSI < 35, Preis nahe EMA"
    elif rsi > 70 and price <= ema * 1.005:
        signal = "SHORT"
        reason = "RSI > 70, Preis nahe EMA"
    elif volume > 1.5 * avg_volume:
        signal = "BREAKOUT"
        reason = f"Volumenanstieg ({volume:.0f} > Ø{avg_volume:.0f})"

    icon = "✅" if signal == "LONG" else "❌" if signal == "SHORT" else "⚡" if signal == "BREAKOUT" else "➖"
    message = (
        f"{icon} {symbol} Signal: {signal}\n"
        f"Grund: {reason}\n"
        f"RSI: {rsi:.2f}, MACD: {macd_line:.4f}, EMA: {ema:.2f}, Preis: {price}, Volumen: {volume:.0f}\n"
        f"Zeit: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )
    return message if signal != "NEUTRAL" else None

def check_all_symbols():
    symbols = [
        'LINKUSDT', 'ENAUSDT', 'MOVEUSDT', 'ONDOUSDT', 'XRPUSDT', 'ETHUSDT',
        'SOLUSDT', 'LTCUSDT', 'ADAUSDT', 'BTCUSDT', 'SUIUSDT', 'HBARUSDT', 'ALGOUSDT',
        'XLMUSDT', 'PEPEUSDT', 'SXTUSDT', 'SOLVUSDT', 'INITUSDT', 'ZEREBROUSDT',
        'BNBUSDT', 'TRXUSDT', 'AVAXUSDT', 'SHIBUSDT', 'HYPEUSDT', 'TAOUSDT', 'AAVEUSDT',
        'APTUSDT', 'KASUSDT', 'VETUSDT', 'POLUSDT', 'FILUSDT', 'JUPUSDT', 'MKRUSDT',
        'DEXEUSDT', 'GALAUSDT', 'SOLAYERUSDT', 'DOGEUSDT', 'OPUSDT', 'ARBUSDT',
        'SEIUSDT', 'WIFUSDT', 'PYTHUSDT', 'TIAUSDT', 'RNDRUSDT', 'STXUSDT', 'NEARUSDT',
        'INJUSDT', 'RUNEUSDT', 'TURBOUSDT', 'JOEUSDT', 'IDUSDT', 'LDOUSDT'
    ]
    for symbol in symbols:
        try:
            df = get_klines(symbol)
            signal = analyze(df, symbol)
            if signal:
                send_telegram(signal)
                print(signal)
            else:
                print(f"{symbol}: Kein Signal.")
        except Exception as e:
            print(f"Fehler bei {symbol}: {e}")

def run_bot():
    while True:
        check_all_symbols()
        time.sleep(300)

if __name__ == "__main__":
    send_telegram("Bot wurde gestartet (optimierte Logik).")
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=8080)


