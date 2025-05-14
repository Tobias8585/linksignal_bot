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
    payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("Telegram-Fehler:", e)

def get_klines(symbol, interval="1m", limit=100):
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
    if df is None or len(df) < 50:
        print(f"{symbol}: Zu wenig Daten für Analyse ({0 if df is None else len(df)} Kerzen)", flush=True)
        return None

    rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    ema = df['close'].ewm(span=20).mean().iloc[-1]
    macd_line = MACD(df['close']).macd().iloc[-1]
    price = df['close'].iloc[-1]
    atr = (df['high'] - df['low']).rolling(window=14).mean().iloc[-1]
    volume = df['volume'].iloc[-1]
    avg_volume = df['volume'].rolling(window=20).mean().iloc[-1]

    long_signals = sum([rsi < 65, macd_line > -1, price > ema])
    short_signals = sum([rsi > 70, macd_line < 0, price < ema])


print(
    f"{symbol}: "
    f"Long-Signals={long_signals}, Short-Signals={short_signals}, "
    f"RSI={rsi:.2f}, MACD={macd_line:.4f}, Preis={price:.4f}, EMA={ema:.4f}",
    flush=True
)


    signal = "NEUTRAL"
    reason = ""

    if long_signals >= 2 and long_signals >= short_signals:
        signal = "LONG"
        reason = "Mindestens 2 Long-Kriterien erfüllt"
    elif short_signals >= 2 and short_signals >= long_signals:
        signal = "SHORT"
        reason = "Mindestens 2 Short-Kriterien erfüllt"
    elif long_signals == 1 and short_signals == 0:
        signal = "LONG"
        reason = "1 Long-Kriterium ohne Short-Signale"
    elif short_signals == 1 and long_signals == 0:
        signal = "SHORT"
        reason = "1 Short-Kriterium ohne Long-Signale"
    else:
        reason = "Zu wenig Übereinstimmung für ein Signal"

    if signal == "NEUTRAL":
        print(
            f"{symbol}: Kein Signal – RSI={rsi:.2f}, MACD={macd_line:.4f}, Preis={price:.4f}, EMA={ema:.4f}, "
            f"Long={long_signals}, Short={short_signals} | Grund: {reason}",
            flush=True
        )

    return signal if signal != "NEUTRAL" else None



    tp1 = price + 1.5 * atr if signal == "LONG" else price - 1.5 * atr
    tp2 = price + 2.5 * atr if signal == "LONG" else price - 2.5 * atr
    sl = price - 1.2 * atr if signal == "LONG" else price + 1.2 * atr

    msg = (
        f"🔔 *{symbol}* Signal: *{signal}*\n"
        f"🧠 Grund: {reason}\n"
        f"📊 RSI: {rsi:.2f} | MACD: {macd_line:.4f} | EMA: {ema:.2f}\n"
        f"🔥 Preis: {price:.4f} | Vol: {volume:.0f} vs Ø{avg_volume:.0f}\n"
        f"🎯 TP1: {tp1:.4f} | TP2: {tp2:.4f} | SL: {sl:.4f}\n"
        f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )

    print(
        f"{symbol}: SIGNAL={signal} | RSI={rsi:.2f}, MACD={macd_line:.4f}, Preis={price:.4f}, EMA={ema:.4f}, "
        f"Vol={volume:.0f}/Ø{avg_volume:.0f}, TP1={tp1:.4f}, SL={sl:.4f}",
        flush=True
    )

    return msg



# alle Symbole unverändert übernommen
def check_all_symbols():
    symbols = [  # alle deine originalen Coins – keine Änderung hier
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "SOLUSDT", "DOGEUSDT", "AVAXUSDT", "TRXUSDT", "DOTUSDT",
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
    ]

    for symbol in symbols:
        df = get_klines(symbol)
        if df is not None:
            signal = analyze(df, symbol)
            if signal:
                send_telegram(signal)
                print(f"Telegram gesendet: {symbol}\nInhalt: {signal}", flush=True)
        else:
            print(f"{symbol}: Keine Daten vom Server", flush=True)

def run_bot():
    while True:
        check_all_symbols()
        time.sleep(300)

@app.route('/')
def home():
    return "Bot läuft und empfängt Anfragen."

if __name__ == "__main__":
    send_telegram("🚀 Bot wurde gestartet und überwacht Coins mit gelockerten Bedingungen.")
    print("Telegram-Startnachricht wurde gesendet.", flush=True)
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=8080)

