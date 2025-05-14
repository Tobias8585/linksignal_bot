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

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("Telegram-Fehler:", e)

def get_klines(symbol, interval="1h", limit=100):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        data = requests.get(url).json()
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
        print(f"Klines-Fehler bei {symbol}: {e}")
        return None

def analyze(df, symbol):
    if df.empty:
        return None

    rsi = RSIIndicator(close=df['close']).rsi().iloc[-1]
    macd_line = MACD(close=df['close']).macd_diff().iloc[-1]
    ema = EMAIndicator(close=df['close'], window=20).ema_indicator().iloc[-1]

    price = df['close'].iloc[-1]
    atr = (df['high'] - df['low']).rolling(window=14).mean().iloc[-1]
    volume = df['volume'].iloc[-1]
    avg_volume = df['volume'].rolling(window=20).mean().iloc[-1]

    long_signals = sum([rsi < 55, macd_line > 0, price > ema])
    short_signals = sum([rsi > 45, macd_line < 0, price < ema])

    signal = "NEUTRAL"
    reason = ""
    if long_signals >= 1:
        signal = "LONG"
        reason = f"{long_signals}/3 Kriterien für LONG erfüllt"
    elif short_signals >= 1:
        signal = "SHORT"
        reason = f"{short_signals}/3 Kriterien für SHORT erfüllt"

    quality = "⭐⭐⭐" if abs(rsi - 50) > 20 and volume > avg_volume * 1.5 else "⭐⭐"
    icon = "✅" if signal == "LONG" else "❌" if signal == "SHORT" else "⚡"

    tp1 = price + 1.5 * atr if signal == "LONG" else price - 1.5 * atr
    tp2 = price + 2.5 * atr if signal == "LONG" else price - 2.5 * atr
    sl = price - 1.2 * atr if signal == "LONG" else price + 1.2 * atr

    msg = (
        f"{icon} *{symbol}* Signal: *{signal}*\n"
        f"📝 Grund: {reason}\n"
        f"📊 RSI: {rsi:.2f} | MACD: {macd_line:.4f} | EMA: {ema:.2f}\n"
        f"💰 Preis: {price:.4f} | Vol: {volume:.0f} vs Ø{avg_volume:.0f}\n"
        f"🎯 TP1: {tp1:.4f} | TP2: {tp2:.4f} | SL: {sl:.4f}\n"
        f"⭐️ Signalqualität: {quality}\n"
        f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )

    print(f"[{symbol}] Ergebnis: Signal={signal}, LONG={long_signals}/3, SHORT={short_signals}/3")

    return msg if signal != "NEUTRAL" else None


def check_all_symbols():
    symbols = [ "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "SOLUSDT", "DOGEUSDT", "AVAXUSDT", "TRXUSDT", "DOTUSDT",
    "MATICUSDT", "LTCUSDT", "SHIBUSDT", "LINKUSDT", "ATOMUSDT", "UNIUSDT", "XLMUSDT", "HBARUSDT", "APTUSDT", "ARBUSDT",
    "VETUSDT", "ICPUSDT", "NEARUSDT", "FILUSDT", "INJUSDT", "RENDERUSDT", "QNTUSDT", "LDOUSDT", "EGLDUSDT", "AAVEUSDT",
    "SANDUSDT", "MANAUSDT", "THETAUSDT", "AXSUSDT", "XTZUSDT", "CHZUSDT", "GRTUSDT", "ENSUSDT", "KAVAUSDT", "TWTUSDT",
    "FXSUSDT", "RLCUSDT", "PEPEUSDT", "SUIUSDT", "FLUXUSDT", "CELOUSDT", "STXUSDT", "COMPUSDT", "ZILUSDT", "ZENUSDT",
    "YFIUSDT", "DYDXUSDT", "SNXUSDT", "BANDUSDT", "LRCUSDT", "DASHUSDT", "CRVUSDT", "KSMUSDT", "ALICEUSDT", "GALAUSDT",
    "ONEUSDT", "ARPAUSDT", "RNDRUSDT", "TOMOUSDT", "OCEANUSDT", "CKBUSDT", "BLZUSDT", "ILVUSDT", "YGGUSDT", "BICOUSDT",
    "JOEUSDT", "HOOKUSDT", "HIGHUSDT", "XNOUSDT", "LOOMUSDT", "TRUUSDT", "PERPUSDT", "BAKEUSDT", "STMXUSDT", "ACHUSDT",
    "NKNUSDT", "ALPHAUSDT", "CTSIUSDT", "ANKRUSDT", "SKLUSDT", "ZRXUSDT", "AGIXUSDT", "PLAUSDT", "API3USDT", "BELUSDT",
    "MOVRUSDT", "BNTUSDT", "DENTUSDT", "GLMRUSDT", "DEGOUSDT", "KNCUSDT", "QUICKUSDT", "TRBUSDT", "HYPEUSDT", "TAOUSDT",
    "KASUSDT", "POLUSDT", "JUPUSDT", "MKRUSDT", "DEXEUSDT", "SOLAYERUSDT", "SXTUSDT", "INITUSDT", "ZEREBROUSDT",
    "JTOUSDT", "PYTHUSDT", "ONDOUSDT", "ENAUSDT", "TNSRUSDT", "WUSDT", "NOTUSDT", "PIXELUSDT", "AEVOUSDT", "TURBOUSDT",
    "MOGUSDT", "DYMUSDT", "PORTALUSDT", "1000SATSUSDT", "LINAUSDT", "IDEXUSDT", "SPELLUSDT", "FETUSDT", "LITUSDT",
    "CVCUSDT", "COTIUSDT", "REEFUSDT", "LQTYUSDT", "NMRUSDT", "RSRUSDT", "MTLUSDT", "PHBUSDT", "GALUSDT", "WNXMUSDT",
    "BONDUSDT", "FLOKIUSDT", "ALPACAUSDT", "XVGUSDT", "BTSUSDT", "SFPUSDT", "VTHOUSDT", "TRACUSDT", "ANTUSDT",
    "POWRUSDT", "USTCUSDT", "STRAXUSDT", "MDTUSDT", "DGBUSDT", "BADGERUSDT", "AUDIOUSDT", "XECUSDT", "VOXELUSDT",
    "TUSDT", "LPTUSDT", "MLNUSDT", "TVKUSDT", "UNFIUSDT", "FORTHUSDT", "RUNEUSDT", "ERNUSDT", "FARMUSDT", "DUSKUSDT",
    "XVSUSDT", "SUNUSDT", "BETAUSDT", "ASTRUSDT", "AERGOUSDT", "GHSTUSDT", "ALCXUSDT", "REIUSDT", "PUNDIXUSDT",
    "KLAYUSDT", "OXTUSDT", "KEYUSDT", "ACMUSDT", "WAVESUSDT", "XRP3LUSDT", "JOEYUSDT", "RAYUSDT", "MBLUSDT", "TRBUSD",
    "JAMUSDT", "ARKMUSDT", "NTRNUSDT", "ETHFIUSDT", "ALTUSDT", "BEAMUSDT", "STORJUSDT", "TOMO3SUSDT", "MANTAUSDT",
    "XAIUSDT", "NFPUSDT", "MAVUSDT", "ZKUSDT", "PYRUSDT", "BICO3LUSDT", "SANTOSUSDT", "JSTUSDT", "LOKAUSDT", "GNSUSDT"
 ]  # Beispielkürzung
    for symbol in symbols:
        df = get_klines(symbol)
        if df is not None:
            signal = analyze(df, symbol)
            if signal:
                send_telegram(signal)
                print(
                    f"Telegram gesendet:\n"
                    f"Symbol: {symbol}\n"
                    f"Inhalt:\n{signal}"
                )


def run_bot():
    while True:
        check_all_symbols()
        time.sleep(300)

@app.route('/')
def home():
    return "Bot läuft und empfängt Anfragen."

if __name__ == "__main__":
    send_telegram("🚀 Bot wurde gestartet und überwacht Coins mit gelockerten Bedingungen.")
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=8080)
