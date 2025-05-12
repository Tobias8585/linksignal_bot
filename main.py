import requests
import time
import threading
from flask import Flask
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, EMAIndicator
from datetime import datetime
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

app = Flask(__name__)

@app.route('/')
def home():
    return "Multi-Coin Signal-Bot läuft."

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("Fehler beim Senden der Nachricht:", e)

def get_klines(symbol):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit=100"
    try:
        response = requests.get(url)
        data = response.json()
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])
        return df
    except Exception as e:
        print(f"Fehler beim Abrufen der Daten für {symbol}: {e}")
        return None

def analyze(df, symbol):
    rsi = RSIIndicator(df['close']).rsi().iloc[-1]
    macd_line = MACD(df['close']).macd().iloc[-1]
    ema = EMAIndicator(df['close']).ema_indicator().iloc[-1]
    price = df['close'].iloc[-1]
    volume = df['volume'].iloc[-1]

    signal = "NEUTRAL"
    if rsi < 35 and macd_line > 0 and price > ema:
        signal = "LONG"
    elif rsi > 70 and macd_line < 0 and price < ema:
        signal = "SHORT"

    icon = "✅" if signal == "LONG" else "❌" if signal == "SHORT" else "➖"
    message = (
        f"{icon} {symbol} Signal: {signal}\n"
        f"RSI: {rsi:.2f}, MACD: {macd_line:.4f}, Volumen: {volume}\n"
        f"Zeit: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )
    return message if signal != "NEUTRAL" else None

def check_all_symbols():
    symbols = [
        'LINKUSDT', 'ENAUSDT', 'MOVEUSDT', 'ONDOUSDT', 'XRPUSDT', 'ETHUSDT',
        'SOLUSDT', 'LTCUSDT', 'ADAUSDT', 'BTCUSDT', 'SUIUSDT', 'HBARUSDT', 'ALGOUSDT',
        'PEPEUSDT', 'SXTUSDT', 'SOLVUSDT', 'INITUSDT', 'ZEREBROUSDT',
        'BNBUSDT', 'TRXUSDT', 'AVAXUSDT', 'SHIBUSDT', 'HYPEUSDT', 'TAOUSDT', 'AAVEUSDT',
        'APTUSDT', 'KASUSDT', 'VETUSDT', 'POLUSDT', 'FILUSDT', 'JUPUSDT', 'MKRUSDT',
        'DEXEUSDT', 'GALAUSDT', 'SOLAYERUSDT'
    ]
    for symbol in symbols:
        df = get_klines(symbol)
        if df is not None:
            signal_msg = analyze(df, symbol)
            if signal_msg:
                send_telegram(signal_msg)
                print(signal_msg)
            else:
                print(f"{symbol}: Kein Signal.")
        else:
            print(f"{symbol}: Datenabruf fehlgeschlagen.")

def run_bot():
    while True:
        check_all_symbols()
        time.sleep(300)

if __name__ == "__main__":
    send_telegram("Bot wurde gestartet und ist bereit.")
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=8080)


