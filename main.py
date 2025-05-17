import requests
import time
import threading
from flask import Flask
from bs4 import BeautifulSoup
import pytz
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD, CCIIndicator, IchimokuIndicator
from ta.volatility import BollingerBands
import os
from datetime import datetime
from binance.um_futures import UMFutures

api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")
client = UMFutures(key=api_key, secret=api_secret)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

app = Flask(__name__)
log_file = open("log.txt", "a", encoding="utf-8")

def log_print(message):
    print(message, flush=True)
    log_file.write(f"{message}\n")
    log_file.flush()

CHAT_IDS = [os.getenv("CHAT_ID"), os.getenv("CHAT_ID_2")]  # Haupt- und Kollegen-ID

# Globale Statusvariablen für Timing und Analysen
last_status_time = 0
last_breakout_check = 0
low_coins = []
pre_breakout_coins = []
market_sentiment = {"long": 0, "short": 0}


def send_telegram(message):
    for chat_id in set(CHAT_IDS):
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}
        try:
            response = requests.post(url, json=payload, timeout=5)
            if not response.ok:
                log_print(f"Telegram HTTP-Fehler {response.status_code} bei {chat_id}: {response.text}")
        except requests.exceptions.Timeout:
            log_print(f"Telegram-Timeout bei {chat_id} – Nachricht nicht gesendet.")
        except requests.exceptions.RequestException as e:
            log_print(f"Telegram-Request-Fehler bei {chat_id}: {e}")

# MARKTSTATUS-TIMER
last_status_time = 0

# MARKTFILTER-HILFSFUNKTION
def classify_market_sentiment():
    long_count = market_sentiment["long"]
    short_count = market_sentiment["short"]
    if long_count > short_count * 1.5:
        return "📈 Markt bullisch"
    elif short_count > long_count * 1.5:
        return "📉 Markt bärisch"
    else:
        return "🔄 Markt neutral"

# FUNKTION FÜR TIEFSTANDSANALYSE
def is_near_recent_low(df, window=50, tolerance=0.02):
    current_price = df['close'].iloc[-1]
    recent_low = df['low'].iloc[-window:].min()
    return current_price <= recent_low * (1 + tolerance)

# ERWEITERTE BREAKOUT-VORBEREITUNG mit RSI & CCI
def is_breakout_in_preparation(df, direction="LONG"):
    price = df['close'].iloc[-1]
    recent_high = df['high'].iloc[-21:-1].max()
    recent_low = df['low'].iloc[-21:-1].min()
    volume = df['volume'].iloc[-1]
    avg_volume = df['volume'].rolling(window=20).mean().iloc[-1]
    
    rsi = RSIIndicator(df['close'], window=14).rsi()
    cci = CCIIndicator(high=df['high'], low=df['low'], close=df['close'], window=20).cci()

    # BOT STARTEN UND MARKTSTATUS SENDEN

def run_bot():
    global last_status_time, last_breakout_check
    while True:
        check_all_symbols()

        if time.time() - last_status_time > 3600:
            market_status = classify_market_sentiment()
            low_list_text = ", ".join(low_coins) if low_coins else "-"

            send_telegram(
                f"📊 *Marktstatus-Update*\n"
                f"{market_status}\n"
                f"📈 LONG: {market_sentiment['long']}x | 📉 SHORT: {market_sentiment['short']}x\n"
                f"🟡 {len(low_coins)} Coins nahe ihrem Tiefstand (5m)\n"
                f"🔍 Kandidaten: {low_list_text}"
            )

            last_status_time = time.time()
            low_coins = []

        # Breakout-Vorbereitung alle 15 Minuten
        if time.time() - last_breakout_check > 900:
            if pre_breakout_coins:
                breakout_list = ", ".join(pre_breakout_coins)
                send_telegram(
                    f"🚀 *Breakout-Vorbereitung*\n"
                    f"{len(pre_breakout_coins)} Coins zeigen frühe Breakout-Signale:\n"
                    f"🔍 {breakout_list}"
                )
                pre_breakout_coins = []

            last_breakout_check = time.time()

        time.sleep(600)




def get_klines(symbol, interval="5m", limit=75):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
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
                return df
        except Exception as e:
            log_print(f"{symbol} {interval}: Fehler (Versuch {attempt + 1}/3): {e}")
        time.sleep(2)
    return None

def get_simple_signal(df):
    rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    cci = CCIIndicator(high=df['high'], low=df['low'], close=df['close'], window=20).cci().iloc[-1]
    ema = df['close'].ewm(span=20).mean().iloc[-1]
    ema50 = df['close'].ewm(span=50).mean().iloc[-1]
    macd_line = MACD(df['close']).macd().iloc[-1]
    price = df['close'].iloc[-1]

    long_signals = sum([
        rsi < 35,
        macd_line > 0,
        price > ema * 1.005 and price > ema50,
        cci < -100
    ])
    short_signals = sum([
        rsi > 70,
        macd_line < 0,
        price < ema * 0.995 and price < ema50,
        cci > 100
    ])

    if long_signals >= 2:
        return "LONG", long_signals
    elif short_signals >= 2:
        return "SHORT", short_signals
    return None, 0

def is_reversal_candidate(df):
    rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    cci = CCIIndicator(high=df['high'], low=df['low'], close=df['close'], window=20).cci().iloc[-1]
    macd_line = MACD(df['close']).macd().iloc[-1]
    volume = df['volume'].iloc[-1]
    avg_volume = df['volume'].rolling(20).mean().iloc[-1]

    score = sum([
        rsi < 30,
        cci < -100,
        macd_line > 0,
        volume > avg_volume
    ])
    return score >= 3



def analyze_combined(symbol):
    global market_sentiment, low_coins, pre_breakout_coins

    df_1m = get_klines(symbol, interval="1m", limit=50)
    df_5m = get_klines(symbol, interval="5m", limit=75)
    if df_1m is None or df_5m is None:
        return None

    signal_1m, count_1m = get_simple_signal(df_1m)
    signal_5m, count_5m = get_simple_signal(df_5m)
    if not signal_1m:
        log_print(f"{symbol}: Kein 1m-Signal")
        return None

    if (signal_1m == "LONG" and signal_5m == "SHORT") or (signal_1m == "SHORT" and signal_5m == "LONG"):
        log_print(f"{symbol}: Divergenz 1m/5m erkannt – kein klares Setup")
        return None

    if signal_1m == "LONG":
        market_sentiment["long"] += 1
    elif signal_1m == "SHORT":
        market_sentiment["short"] += 1

    df = df_5m
    rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    ema = df['close'].ewm(span=20).mean().iloc[-1]
    ema50 = df['close'].ewm(span=50).mean().iloc[-1]
    ema_prev = df['close'].ewm(span=20).mean().iloc[-2]
    ema50_prev = df['close'].ewm(span=50).mean().iloc[-2]
    ema_trend_down = ema < ema_prev
    ema50_trend_down = ema50 < ema50_prev

    macd = MACD(df['close'])
    macd_line = macd.macd().iloc[-1]
    macd_signal = macd.macd_signal().iloc[-1]
    macd_cross = macd_line > macd_signal if signal_1m == "LONG" else macd_line < macd_signal
    price = df['close'].iloc[-1]

    recent_high = df['high'].iloc[-50:].max()
    recent_low = df['low'].iloc[-50:].min()
    fib_618 = recent_low + 0.618 * (recent_high - recent_low)
    fib_signal = (signal_1m == "LONG" and price > fib_618) or (signal_1m == "SHORT" and price < fib_618)

    bb = BollingerBands(close=df['close'], window=20, window_dev=2)
    bb_upper = bb.bollinger_hband().iloc[-1]
    bb_lower = bb.bollinger_lband().iloc[-1]
    bollinger_signal = (signal_1m == "LONG" and price < bb_lower) or (signal_1m == "SHORT" and price > bb_upper)

    ichimoku = IchimokuIndicator(high=df['high'], low=df['low'], window1=9, window2=26, window3=52)
    kijun_sen = ichimoku.ichimoku_base_line().iloc[-1]
    if signal_1m == "LONG" and price < kijun_sen:
        log_print(f"{symbol}: LONG aber unter Ichimoku-Kijun")
        return None
    if signal_1m == "SHORT" and price > kijun_sen:
        log_print(f"{symbol}: SHORT aber über Ichimoku-Kijun")
        return None

    atr = (df['high'] - df['low']).rolling(window=14).mean().iloc[-1]
    volatility_pct = atr / price * 100

    volume = df['volume'].iloc[-1]
    avg_volume = df['volume'].rolling(window=20).mean().iloc[-1]

    if atr < price * 0.003:
        log_print(f"{symbol}: Kein Signal – ATR zu niedrig")
        return None

    breakout = (signal_1m == "LONG" and price > df['high'].iloc[-21:-1].max()) or                (signal_1m == "SHORT" and price < df['low'].iloc[-21:-1].min())
    strong_volume = volume > avg_volume * 1.3
    ema_cross = ema > ema50 if signal_1m == "LONG" else ema < ema50

    if count_1m == 2:
        if not (strong_volume and breakout):
            log_print(f"{symbol}: 2/3 aber kein Breakout oder Volumen")
            return None
        if signal_1m == "SHORT" and not (ema_trend_down and ema50_trend_down):
            log_print(f"{symbol}: 2/3 SHORT aber Trend nicht fallend")
            return None

    pre_breakout = is_breakout_in_preparation(df, direction=signal_1m)
    if pre_breakout:
        pre_breakout_coins.append(symbol)

    if is_near_recent_low(df, window=50, tolerance=0.02):
        low_coins.append(symbol)

       # 📉 Reversal-Check
    if is_reversal_candidate(df):
        send_telegram(f"🔄 *Reversal-Kandidat erkannt*: {symbol}\n"
                      f"Coin zeigt starke Umkehrsignale (RSI/CCI/MACD/Volumen).")

    criteria_count = (
        count_1m +
        int(strong_volume) +
        int(breakout) +
        int(pre_breakout is True) +
        int(macd_cross) +
        int(ema_cross) +
        int(bollinger_signal) +
        int(fib_signal)
    )

    if criteria_count >= 7:
        stars = "⭐⭐⭐"
        signal_strength = "🟢 Sehr starkes Signal"
    elif criteria_count >= 5:
        stars = "⭐⭐"
        signal_strength = "🟡 Gutes Signal"
    elif criteria_count >= 3:
        stars = "⭐"
        signal_strength = "🔸 Mögliches Signal"
    else:
        return None

    if volatility_pct < 0.5:
        tp1_factor, tp2_factor, sl_factor = 1.2, 1.8, 1.0
    elif volatility_pct < 1.5:
        tp1_factor, tp2_factor, sl_factor = 1.5, 2.5, 1.2
    else:
        tp1_factor, tp2_factor, sl_factor = 1.8, 3.0, 1.4

    tp1 = price + tp1_factor * atr if signal_1m == "LONG" else price - tp1_factor * atr
    tp2 = price + tp2_factor * atr if signal_1m == "LONG" else price - tp2_factor * atr
    sl = price - sl_factor * atr if signal_1m == "LONG" else price + sl_factor * atr

    trend_text = "Seitwärts"
    if price > ema and price > ema50:
        trend_text = "Aufwärts"
    elif price < ema and price < ema50:
        trend_text = "Abwärts"

    rsi_zone = "neutral"
    if rsi < 30:
        rsi_zone = "überverkauft"
    elif rsi > 70:
        rsi_zone = "überkauft"

    macd_text = "MACD-Cross: ✅" if macd_cross else "MACD-Cross: ❌"
    bollinger_text = "Bollinger-Rebound: ✅" if bollinger_signal else "Bollinger-Rebound: ❌"
    fib_text = "Fibonacci-Bestätigung: ✅" if fib_signal else "Fibonacci-Bestätigung: ❌"
    breakout_text = "🚀 Breakout erkannt!" if breakout else ""


    msg = (
        f"🔔 *{symbol}* Signal: *{signal_1m}* {stars}\n"
        f"{signal_strength}\n"
        f"{breakout_text}\n"
        f"🧠 Grund: {count_1m} von 3 {signal_1m}-Kriterien erfüllt\n"
        f"🧠 Hauptsignal aus 1m | 5m: {signal_5m or 'kein'}\n"
        f"📈 Trend: {trend_text} | RSI-Zone: {rsi_zone} | Volatilität: {volatility_pct:.2f} %\n"
        f"{macd_text} | EMA-Cross: {'✅' if ema_cross else '❌'} | {bollinger_text} | {fib_text}\n"
        f"📊 RSI: {rsi:.2f} | MACD: {macd_line:.4f} | EMA20: {ema:.2f} | EMA50: {ema50:.2f}\n"
        f"🔥 Preis: {price:.4f} | Vol: {volume:.0f} vs Ø{avg_volume:.0f}\n"
        f"🎯 TP1: {tp1:.4f} | TP2: {tp2:.4f} | SL: {sl:.4f}\n"
        f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
    )

    return msg


def get_top_volume_symbols(limit=100):
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        response = requests.get(url, timeout=5)
        data = response.json()
        sorted_data = sorted(
            [s for s in data if s['symbol'].endswith('USDT')],
            key=lambda x: float(x['quoteVolume']),
            reverse=True
        )
        return [s['symbol'] for s in sorted_data[:limit]]
    except Exception as e:
        log_print(f"Fehler beim Laden der Volume-Daten: {e}")
        return []


def check_all_symbols():
    global market_sentiment
    market_sentiment["long"] = 0
    market_sentiment["short"] = 0

    try:
        exchange_info = client.exchange_info()
        symbols = [
            s['symbol'] for s in exchange_info['symbols']
            if s['contractType'] == 'PERPETUAL' and s['symbol'].endswith("USDT")
        ]
    except Exception as e:
        log_print(f"Fehler beim Laden der Symbolliste: {e}")
        return

    symbols = get_top_volume_symbols(limit=100)  # ✅ richtig eingerückt

    if not symbols:
        log_print("Keine Symbole zum Prüfen verfügbar.")
        return

    for symbol in symbols:
        signal = analyze_combined(symbol)
        if signal:
            send_telegram(signal)
            log_print(f"{symbol}: Signal gesendet\n{signal}")
        else:
            log_print(f"{symbol}: Kein Signal")
        time.sleep(1)

    log_print(f"📊 Marktbreite: {market_sentiment['long']}x LONG | {market_sentiment['short']}x SHORT")


@app.route('/')
def home():
    return "Bot mit primärer 1m-Analyse läuft."


@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    symbol = data.get('symbol')
    note = data.get('note', '')
    if symbol:
        log_print(f"Webhook erhalten für {symbol} – Hinweis: {note}")
        send_telegram(f"🔔 Webhook-Trigger für *{symbol}*\nHinweis: {note}")
        return {"status": "received"}, 200
    else:
        return {"error": "symbol fehlt"}, 400




if __name__ == "__main__":
    send_telegram("🚀 Bot wurde mit Doppelanalyse gestartet.")
    log_print("Telegram-Startnachricht wurde gesendet.")
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=8080)
