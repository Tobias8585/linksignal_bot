import requests
import time
import threading
import schedule
from flask import Flask
from bs4 import BeautifulSoup
import pytz
from pytz import timezone
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator, MACD, CCIIndicator, IchimokuIndicator, ADXIndicator
from ta.volatility import BollingerBands
import os
from datetime import datetime, timedelta
from binance.um_futures import UMFutures

api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")
client = UMFutures(key=api_key, secret=api_secret)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# 🌍 Globale Zähler für Marktbreite
total_long_signals = 0
total_short_signals = 0


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
btc_strength_ok = True  # BTC-Stärke-Standardwert, wird beim Start als "stark" angenommen


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
def classify_market_sentiment_from_results(results):
    long_count = sum(1 for r in results if r == "LONG")
    short_count = sum(1 for r in results if r == "SHORT")

    if long_count > short_count * 1.5:
        return "📈 Markt bullisch", long_count, short_count
    elif short_count > long_count * 1.5:
        return "📉 Markt bärisch", long_count, short_count
    else:
        return "🔄 Markt neutral", long_count, short_count


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
    # Prüfe starke Preisänderung mit abgestufter Volumenwarnung
    price_change_pct = abs(df['close'].iloc[-1] - df['open'].iloc[-1]) / df['open'].iloc[-1] * 100
    if price_change_pct > 1.5:
        if volume < avg_volume * 0.6:
            log_print(f"{symbol}: Preisbewegung > 1.5 %, aber Volumen deutlich zu gering – kein Signal")
            return None, f"{symbol}: Signal blockiert – starker Move mit extrem schwachem Volumen"
        elif volume < avg_volume * 0.9:
            log_print(f"{symbol}: Preisbewegung > 1.5 %, Volumen unterdurchschnittlich – Warnung")

    rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    cci = CCIIndicator(high=df['high'], low=df['low'], close=df['close'], window=20).cci().iloc[-1]

    near_high = price >= recent_high * 0.985
    near_low = price <= recent_low * 1.015
    rising_volume = volume > avg_volume * 0.9

    if direction == "LONG":
        return near_high and rising_volume and rsi > 50 and cci > 0
    elif direction == "SHORT":
        return near_low and rising_volume and rsi < 50 and cci < 0
    return False


    # BOT STARTEN UND MARKTSTATUS SENDEN


def run_bot():
    global last_status_time, last_breakout_check, low_coins, pre_breakout_coins, all_signal_results

    schedule.every().day.at("07:00").do(check_market_events)

    while True:
        # 👉 BTC-Stärkeprüfung vor Symbolanalyse einbauen
        check_btc_strength()

        check_all_symbols()
        schedule.run_pending()

        if time.time() - last_status_time > 3600:
            market_status, long_count, short_count = classify_market_sentiment_from_results(all_signal_results)
            log_print(f"{len(all_signal_results)} Coins ausgewertet für Marktstatus")
            low_list_text = ", ".join(low_coins) if low_coins else "-"

            # 🧠 Tendenz aus Marktstruktur ableiten
            if market_bullish_count > market_bearish_count * 1.2:
                market_trend = "📈 *Bullish*"
            elif market_bearish_count > market_bullish_count * 1.2:
                market_trend = "📉 *Bearish*"
            else:
                market_trend = "⚖️ *Neutral*"

            # BTC-Stärke
            status_btc = "🟢 stark" if btc_strength_ok else "🔴 schwach"

            # 📦 Kompakte Gesamt-Nachricht
            summary_message = (
                f"📊 *Marktanalyse Übersicht*\n\n"
                f"🧭 *Marktstruktur:*\n"
                f"🟢 {market_bullish_count} bullish | 🔴 {market_bearish_count} bearish | ⚪️ {market_neutral_count} neutral\n"
                f"→ Tendenz: {market_trend}\n\n"
                f"📉 *Tiefstände:*\n"
                f"🔻 72h-Tiefstand: {len(low_coins)} Coins\n"
                f"🔍 Kandidaten (5m): {low_list_text}\n\n"
                f"🪙 *BTC-Stärke:* {status_btc}"
                f"🔍 *Anzahl analysierter Coins:* {len(symbols)}"
            )

            try:
                send_telegram(summary_message)
            except Exception as e:
                log_print(f"❌ Fehler bei Marktanalyse-Telegramnachricht: {e}")

            last_status_time = time.time()
            low_coins = []
           


        if time.time() - last_breakout_check > 900:
            if pre_breakout_coins:
                breakout_list = ", ".join(pre_breakout_coins)
                send_telegram(
                    f"🚀 *Breakout-Vorbereitung erkannt*\n"
                    f"{len(pre_breakout_coins)} Coins zeigen Anzeichen für einen bevorstehenden Ausbruch:\n"
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


def check_btc_strength():
    global btc_strength_ok

    # Versuche BTC-Daten zu laden
    df = get_klines('BTCUSDT', interval='5m', limit=50)
    if df is None:
        log_print("BTC-Daten konnten nicht geladen werden")
        btc_strength_ok = True  # Annahme: lieber 'stark', um keine Signale zu blockieren
        return  # Funktion hier abbrechen – sonst würde df == None zu Fehlern führen

    # Berechne technische Indikatoren für BTC
    rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    ema = df['close'].ewm(span=20).mean().iloc[-1]
    ema50 = df['close'].ewm(span=50).mean().iloc[-1]
    macd = MACD(df['close']).macd().iloc[-1]
    price = df['close'].iloc[-1]

    # BTC wird als "stark" gewertet, wenn RSI > 50, MACD positiv und Preis über beiden EMAs liegt
    btc_strength_ok = (rsi > 50) and (macd > 0) and (price > ema and price > ema50)
    status = "🟢 stark" if btc_strength_ok else "🔴 schwach"
    log_print(f"BTC-Marktstärke: {status}")


def get_simple_signal(df):
    signal_direction = None
    count = 0

    # RSI prüfen
    rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    if rsi < 38:
        signal_direction = "LONG"
        count += 1
    elif rsi > 67:
        signal_direction = "SHORT"
        count += 1
        
# MACD prüfen (gelockert – auch fast gleich erlaubt)
    macd = MACD(df['close'])
    macd_line = macd.macd().iloc[-1]
    macd_signal = macd.macd_signal().iloc[-1]
    macd_diff = macd_line - macd_signal

    if signal_direction == "LONG" and macd_diff > -0.003:
        count += 1
    elif signal_direction == "SHORT" and macd_diff < 0.003:
        count += 1

    return signal_direction, count
    
def is_reversal_candidate(df):
    rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    cci = CCIIndicator(high=df['high'], low=df['low'], close=df['close'], window=20).cci().iloc[-1]
    macd = MACD(df['close'])
    macd_line = macd.macd().iloc[-1]
    macd_signal = macd.macd_signal().iloc[-1]
    volume = df['volume'].iloc[-1]
    avg_volume = df['volume'].rolling(window=20).mean().iloc[-1]

    # Preisbewegung prüfen
    price_change_pct = abs(df['close'].iloc[-1] - df['open'].iloc[-1]) / df['open'].iloc[-1] * 100
    if price_change_pct > 1.5 and volume < avg_volume * 0.6:
        log_print(f"{symbol}: ❌ Reversal abgebrochen – starker Move bei sehr geringem Volumen")
        return False, None
    elif price_change_pct > 1.5 and volume < avg_volume * 0.9:
        log_print(f"{symbol}: ⚠️ Reversal-Warnung – Volumen leicht unterdurchschnittlich")

    # Kriterien für Long-Reversal
    if rsi < 30 and cci < -100 and macd_line > macd_signal:
        return True, "LONG"
    # Kriterien für Short-Reversal
    elif rsi > 70 and cci > 100 and macd_line < macd_signal:
        return True, "SHORT"
    else:
        return False, None



    is_macd_cross = macd_line > macd_signal or macd_line < macd_signal
    is_rsi_extreme = rsi < 30 or rsi > 70
    is_cci_extreme = cci < -100 or cci > 100
    is_volume_spike = volume > avg_volume * 1.5

    return is_macd_cross and is_rsi_extreme and is_cci_extreme and is_volume_spike




def analyze_combined(symbol):
    global market_sentiment, low_coins, pre_breakout_coins, btc_strength_ok

    market_bias_warning = ""

    df_1m = get_klines(symbol, interval="1m", limit=50)
    df_5m = get_klines(symbol, interval="5m", limit=300)

    # ✅ Datentyp-Sicherheit für numerische Vergleiche
    df_1m['open'] = df_1m['open'].astype(float)
    df_1m['high'] = df_1m['high'].astype(float)
    df_1m['low'] = df_1m['low'].astype(float)
    df_1m['close'] = df_1m['close'].astype(float)

    df_5m['open'] = df_5m['open'].astype(float)
    df_5m['high'] = df_5m['high'].astype(float)
    df_5m['low'] = df_5m['low'].astype(float)
    df_5m['close'] = df_5m['close'].astype(float)

    if df_1m is None or df_5m is None:
        return None, None


    signal_1m, count_1m = get_simple_signal(df_1m)
    signal_5m, count_5m = get_simple_signal(df_5m)

    if not signal_1m and not signal_5m:
        log_print(f"{symbol}: Kein Signal in 1m oder 5m – übersprungen")
        return None, None

    if not btc_strength_ok and signal_1m == "LONG":
        log_print(f"{symbol}: ⚠️ BTC schwach – Vorsicht bei LONG-Signal")

    if (signal_1m == "LONG" and signal_5m == "SHORT") or (signal_1m == "SHORT" and signal_5m == "LONG"):
        log_print(f"{symbol}: ⚠️ Divergenz 1m vs. 5m – Qualitätsrisiko")
        divergence_warning = True  # Optional: für späteren Hinweis im Telegram-Text


    df = df_5m
    df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].astype(float)

    price = df['close'].iloc[-1]
    candle_close = df['close'].iloc[-1]
    candle_open = df['open'].iloc[-1]
    volume = df['volume'].iloc[-1]
    avg_volume = df['volume'].rolling(window=20).mean().iloc[-1]
    # Prüfe starke Preisänderung mit schwachem Volumen
    price_change_pct = abs(df['close'].iloc[-1] - df['open'].iloc[-1]) / df['open'].iloc[-1] * 100
    if price_change_pct > 1.5 and volume < avg_volume:
        log_print(f"{symbol}: Preisbewegung > 1.5 %, aber Volumen zu gering – kein Signal")
        return None, f"{symbol}: Kein Signal – starke Preisbewegung bei schwachem Volumen"

    prev_resistance = df['high'].iloc[-21:-1].max()
    prev_support = df['low'].iloc[-21:-1].min()

    breakout = (price > prev_resistance) if signal_1m == "LONG" else (price < prev_support)

    if breakout and signal_1m == "LONG" and price > prev_resistance * 1.01:
        log_print(f"{symbol}: Breakout bereits weit gelaufen – kein Einstieg")
        return None, None
    if breakout and signal_1m == "SHORT" and price < prev_support * 0.99:
        log_print(f"{symbol}: Breakdown bereits weit gelaufen – kein Einstieg")
        return None, None

    if breakout and signal_1m == "LONG":
        if candle_close < prev_resistance or candle_close < candle_open:
            log_print(f"{symbol}: Breakout, aber Candle nicht über Widerstand geschlossen")
            return None, None
        if volume < avg_volume * 1.1:
            log_print(f"{symbol}: Breakout, aber kein signifikantes Volumen")
            return None, None

    if signal_1m == "LONG" and total_short_signals > total_long_signals * 1.5:
        market_bias_warning = "⚠️ *Markt bearish – LONG mit Vorsicht bewerten*"
    elif signal_1m == "SHORT" and total_long_signals > total_short_signals * 1.5:
        market_bias_warning = "⚠️ *Markt bullish – SHORT mit Vorsicht bewerten*"

    ha_close = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    ha_open = ha_close.shift(1).fillna(df['open'])
    last_ha_open = ha_open.iloc[-1]
    last_ha_close = ha_close.iloc[-1]

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

    if len(df) < 20:
        log_print(f"{symbol}: Hinweis – Zu wenig Daten für ADX-/ATR-Berechnung (nur {len(df)} Kerzen)")
        adx = None
        atr = None
        log_print(f"{symbol}: Zu wenig Daten für ADX-/ATR-Berechnung (nur {len(df)} Kerzen)")

    adx = ADXIndicator(df['high'], df['low'], df['close'], window=14).adx().iloc[-1]
    atr = (df['high'] - df['low']).rolling(window=14).mean().iloc[-1]
    volatility_pct = atr / price * 100

    # 🟡 Logging aktivieren
    if pd.isna(adx):
        log_print(f"{symbol}: ⚠️ ADX ist NaN")
    else:
        log_print(f"{symbol}: ADX-Wert liegt bei {adx:.2f}")

    if pd.isna(atr):
        log_print(f"{symbol}: ⚠️ ATR ist NaN")
    else:
        log_print(f"{symbol}: ATR = {atr:.4f} | Volatilität = {volatility_pct:.2f} %")


        # Fehleranalyse
    reasons = []
    if adx < 22.5:
        reasons.append("ADX < 22.5")

    # Neue Heikin-Ashi-Logik: 3 Candles prüfen
    ha_bodies = ha_close[-3:] - ha_open[-3:]
    green_count = sum(1 for x in ha_bodies if x > 0)
    red_count = sum(1 for x in ha_bodies if x < 0)

    if signal_1m == "LONG" and green_count < 2:
        reasons.append("Heikin-Ashi: weniger als 2 von 3 grün")
    if signal_1m == "SHORT" and red_count < 2:
        reasons.append("Heikin-Ashi: weniger als 2 von 3 rot")

    if signal_1m == "LONG" and rsi >= 38:
        reasons.append("RSI nicht im Long-Bereich (<38)")
    if signal_1m == "SHORT" and rsi <= 67:
        reasons.append("RSI nicht im Short-Bereich (>67)")
    if atr < price * 0.003:
        log_print(f"{symbol}: ⚠️ Geringe Volatilität (ATR niedrig) – Signal mit Vorsicht bewerten")
    if signal_1m == "LONG" and ema <= ema50 * 1.005:
        reasons.append("EMA-Trend nicht positiv")
    if signal_1m == "SHORT" and ema >= ema50 * 0.995:
        reasons.append("EMA-Trend nicht negativ")

     # MACD aktiv gegen das Signal?
    if signal_1m == "LONG" and macd_line < macd_signal:
        reasons.append("MACD spricht gegen LONG")
    if signal_1m == "SHORT" and macd_line > macd_signal:
        reasons.append("MACD spricht gegen SHORT")

    log_print(f"{symbol}: Hinweis – MACD-Cross fehlt, aber nicht kritisch")

    if reasons:
        reason_text = f"{symbol}: Kein Signal – " + ", ".join(reasons)
        log_print(reason_text)
        return None, reason_text

    # Weitere Bewertung
    fib_618 = df['low'].iloc[-50:].min() + 0.618 * (df['high'].iloc[-50:].max() - df['low'].iloc[-50:].min())
    fib_signal = (signal_1m == "LONG" and price > fib_618) or (signal_1m == "SHORT" and price < fib_618)

    bb = BollingerBands(close=df['close'], window=20, window_dev=2)
    bb_upper = bb.bollinger_hband().iloc[-1]
    bb_lower = bb.bollinger_lband().iloc[-1]
    bollinger_signal = (signal_1m == "LONG" and price < bb_lower) or (signal_1m == "SHORT" and price > bb_upper)

    ichimoku = IchimokuIndicator(high=df['high'], low=df['low'], window1=9, window2=26, window3=52)
    kijun_sen = ichimoku.ichimoku_base_line().iloc[-1]
    if signal_1m == "LONG" and price < kijun_sen:
        log_print(f"{symbol}: LONG aber unter Ichimoku-Kijun")
        return None, None
    if signal_1m == "SHORT" and price > kijun_sen:
        log_print(f"{symbol}: SHORT aber über Ichimoku-Kijun")
        return None, None

    strong_volume = volume > avg_volume * 1.3
    ema_cross = ema > ema50 * 1.001 if signal_1m == "LONG" else ema < ema50 * 0.999

    if count_1m == 2:
        if not (strong_volume and breakout):
            log_print(f"{symbol}: 2/3 aber kein Breakout oder Volumen")
            return None, None
        if signal_1m == "SHORT" and not (ema_trend_down and ema50_trend_down):
            log_print(f"{symbol}: 2/3 SHORT aber Trend nicht fallend")
            return None, None

    pre_breakout = is_breakout_in_preparation(df, direction=signal_1m)
    if pre_breakout:
        pre_breakout_coins.append(symbol)

    # 72h-Tiefstand erkennen (nur wenn genug Daten vorhanden)
    if len(df) >= 864:
        min_price = df['low'].iloc[-864:].min()
        current_price = df['close'].iloc[-1]
        if current_price <= min_price * 1.005:
            low_coins.append(symbol)

    if is_reversal_candidate(df):
        send_telegram(f"🔄 *Reversal-Kandidat erkannt*: {symbol}\nCoin zeigt starke Umkehrsignale (RSI/CCI/MACD/Volumen).")

        
    # Score-Bewertung
    score = 0
    max_score = 11
    score += 2 if (signal_1m == "LONG" and rsi < 35) or (signal_1m == "SHORT" and rsi > 70) else 0
    score += 2 if breakout else 0
    score += 1.5 if ema_cross else 0
    score += 1.5 if strong_volume else 0
    score += 1 if macd_cross else 0
    score += 1 if bollinger_signal else 0
    score += 1 if fib_signal else 0
    score += 1 if pre_breakout else 0

    percentage = int(min(100, (score / max_score) * 100))
    percentage = max(0, percentage)
    signal_strength = "🟢 Sehr starkes Signal" if score >= 8 else "🟡 Gutes Signal" if score >= 5 else "🔸 Mögliches Signal"
    if score < 3:
        return None, None

    if signal_1m == "LONG":
        current_open = df_1m['open'].iloc[-1]
        current_close = df_1m['close'].iloc[-1]
        if current_close <= current_open:
            log_print(f"{symbol}: Kein Signal – aktuelle Candle fällt")
            return None, None
        last_close = df_1m['close'].iloc[-2]
        last_open = df_1m['open'].iloc[-2]
        if last_close < last_open:
            log_print(f"{symbol}: Kein LONG – letzte abgeschlossene Candle war rot")
            return None, None

    time.sleep(60)
    latest_close = df_1m['close'].iloc[-1]
    latest_open = df_1m['open'].iloc[-1]
    candle_size = abs(latest_close - latest_open) / latest_open

    if signal_1m == "LONG":
        if latest_close < latest_open:
            if candle_size > 0.003:
                log_print(f"{symbol}: ❌ Bestätigungscandle nach 1 Min war klar negativ – Signal verworfen")
                return None, f"{symbol}: Abbruch – negative 1-Minuten-Bestätigung"
            else:
                log_print(f"{symbol}: ⚠️ Bestätigungscandle nach 1 Min war leicht negativ – Warnung")

    if signal_1m == "SHORT":
        if latest_close > latest_open:
            if candle_size > 0.003:
                log_print(f"{symbol}: ❌ Bestätigungscandle nach 1 Min war klar positiv – SHORT-Signal verworfen")
                return None, f"{symbol}: Abbruch – positive 1-Minuten-Bestätigung bei SHORT"
            else:
                log_print(f"{symbol}: ⚠️ Bestätigungscandle nach 1 Min war leicht positiv – Warnung")

    tp1 = price + 1.5 * atr if signal_1m == "LONG" else price - 1.5 * atr
    tp2 = price + 2.5 * atr if signal_1m == "LONG" else price - 2.5 * atr
    sl = price - 1.2 * atr if signal_1m == "LONG" else price + 1.2 * atr
    zurich_time = datetime.now(timezone("Europe/Zurich")).strftime('%d.%m.%Y %H:%M:%S')


    msg = (
        f"🔔 *Signal für: {symbol}* | *{signal_1m}* ({signal_strength})\n"
        f"🟢 *Signalqualität:* {percentage} % erfüllt\n\n"
        f"📊 *Analyse-Zeitrahmen:*\n"
        f"• Hauptsignal: 1m *(50 Minuten Analyse)*\n"
        f"• Bestätigung: 5m *(6 Stunden Analyse)* → {signal_5m or 'kein Signal'}\n"
        f"• Trend: {'Aufwärts' if price > ema and price > ema50 else 'Abwärts' if price < ema and price < ema50 else 'Seitwärts'}\n"
        f"• RSI-Zone: {rsi:.2f}\n"
        f"• ADX (Trendstärke): {adx:.2f}\n"
        f"• Volatilität: {volatility_pct:.2f} %\n\n"
        f"📉 *Indikatoren:*\n"
        f"• MACD-Cross: {'✅' if macd_cross else '❌'}\n"
        f"• EMA-Cross: {'✅' if ema_cross else '❌'}\n"
        f"• Bollinger Rebound: {'✅' if bollinger_signal else '❌'}\n"
        f"• Fibonacci-Bestätigung: {'✅' if fib_signal else '❌'}\n"
        f"• Ichimoku: OK\n\n"
        f"💴 *Preisdaten:*\n"
        f"• Preis: {price:.4f}\n"
        f"• Volumen: {volume:,.0f} vs Ø{avg_volume:,.0f}\n\n"
        f"🎯 *Zielbereiche:*\n"
        f"• TP1: {tp1:.4f}\n"
        f"• TP2: {tp2:.4f}\n"
        f"• SL: {sl:.4f}\n\n"
        f"🕒 *Zeit:* {zurich_time}"
    )

    if market_bias_warning:
        msg += f"\n{market_bias_warning}"
    if signal_1m == "LONG":
        msg += "\n🟢 *BTC stark*" if btc_strength_ok else "\n⚠️ *BTC schwach*: Long-Signal mit Vorsicht bewerten."

    return signal_1m, msg





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
    global market_sentiment, all_signal_results
    global total_long_signals, total_short_signals
    global market_bullish_count, market_bearish_count, market_neutral_count
    global symbols

    all_signal_results = []
    market_sentiment["long"] = 0
    market_sentiment["short"] = 0
    total_long_signals = 0
    total_short_signals = 0
    market_bullish_count = 0
    market_bearish_count = 0
    market_neutral_count = 0

    try:
        exchange_info = client.exchange_info()
        symbols = [
            s['symbol'] for s in exchange_info['symbols']
            if s['contractType'] == 'PERPETUAL' and s['symbol'].endswith("USDT")
        ]
        log_print(f"{len(symbols)} Futures-Coins werden analysiert.")
    except Exception as e:
        log_print(f"Fehler beim Laden der Symbolliste: {e}")
        return

    if not symbols:
        log_print("Keine Symbole zum Prüfen verfügbar.")
        return

    for symbol in symbols:
        # 📊 Marktstruktur zuerst bewerten – unabhängig vom Signal
        try:
            df = get_klines(symbol, interval="5m", limit=50)
            if df is not None:
                rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
                ema20 = EMAIndicator(df['close'], window=20).ema_indicator().iloc[-1]
                ema50 = EMAIndicator(df['close'], window=50).ema_indicator().iloc[-1]

                if rsi > 55 and ema20 > ema50:
                    market_bullish_count += 1
                elif rsi < 45 and ema20 < ema50:
                    market_bearish_count += 1
                else:
                    market_neutral_count += 1
            else:
                log_print(f"{symbol}: Keine Daten für Marktstruktur.")
        except Exception as e:
            log_print(f"{symbol}: Marktstruktur-Bewertung fehlgeschlagen: {e}")

        # 🧠 Jetzt Signalanalyse
        signal_direction, signal_msg = analyze_combined(symbol)

        if signal_direction:
            all_signal_results.append(signal_direction)
            if signal_direction == "LONG":
                total_long_signals += 1
            elif signal_direction == "SHORT":
                total_short_signals += 1

            send_telegram(signal_msg)
            log_print(f"{symbol}: Signal gesendet\n{signal_msg}")
        else:
            all_signal_results.append("NONE")
            log_print(f"{symbol}: Kein Signal")

    # ✅ Nach dem for-Loop: Gesamtstatus berechnen
    if market_sentiment["long"] == 0 and market_sentiment["short"] == 0:
        market_sentiment["status"] = "neutral"

    log_print(f"📊 Marktbreite: {total_long_signals}x LONG | {total_short_signals}x SHORT")

    total_signals = total_long_signals + total_short_signals

    if total_signals > 0:
        long_ratio = total_long_signals / total_signals
        short_ratio = total_short_signals / total_signals

        if long_ratio > 0.6:
            sentiment_text = "📈 Bullish"
        elif short_ratio > 0.6:
            sentiment_text = "📉 Bearish"
        else:
            sentiment_text = "⚖️ Neutral"
    else:
        sentiment_text = "Keine Signale erkannt"

    log_print(f"📊 Marktbreite: {total_long_signals}x LONG | {total_short_signals}x SHORT → Stimmung: {sentiment_text}")




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




def convert_time_ny_to_ch(text_time):
    try:
        ny_tz = pytz.timezone('America/New_York')
        ch_tz = pytz.timezone('Europe/Zurich')
        today = datetime.now(ny_tz).date()
        dt = datetime.strptime(text_time, '%I:%M%p')
        dt = ny_tz.localize(datetime.combine(today, dt.time()))
        dt_ch = dt.astimezone(ch_tz)
        return dt_ch.strftime('%H:%M')
    except Exception:
        return text_time + " (ungültig)"


def check_market_events():
    url = 'https://www.forexfactory.com/calendar'
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers)

    soup = BeautifulSoup(response.text, 'html.parser')
    rows = soup.find_all('tr', class_='calendar__row')

    today = datetime.utcnow().date()
    tomorrow = today + timedelta(days=1)
    valid_days = [today.strftime('%b %d'), tomorrow.strftime('%b %d')]

    events_today = []

    for row in rows:
        date_td = row.find('td', class_='calendar__date')
        impact_td = row.find('td', class_='calendar__impact')
        event_td = row.find('td', class_='calendar__event')
        time_td = row.find('td', class_='calendar__time')
        country_td = row.find('td', class_='calendar__country')

        if not all([date_td, impact_td, event_td, time_td, country_td]):
            continue

        date_text = date_td.text.strip()
        if date_text not in valid_days:
            continue

        impact_level = impact_td.find('span')
        if not impact_level or 'High' not in impact_level.get('title', ''):
            continue

        time_text = time_td.text.strip()
        if time_text.lower() in ['all day', 'tentative', '']:
            continue

        time_ch = convert_time_ny_to_ch(time_text)
        country = country_td.text.strip()
        event = event_td.text.strip()

        if country not in ['USD', 'EUR', 'CHF']:
            continue

        events_today.append(f"{country} {time_ch} – {event}")

    if events_today:
        message = "📅 Wirtschaftskalender heute/morgen:\n\n"
        for e in events_today:
            message += f"🔺 {e}\n"
        message += "\n⚠️ Achtung: hohe Volatilität möglich!"
    else:
        message = "📅 Keine hochrelevanten Wirtschaftsevents heute oder morgen."

    send_telegram(message)



# ⬇️ Erst jetzt darfst du aufrufen:
if __name__ == "__main__":
    send_telegram("🚀 Bot wurde mit Doppelanalyse gestartet.")
    check_market_events()
    log_print("Telegram-Startnachricht wurde gesendet.")
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=8080)
