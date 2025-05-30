from ml_predict import predict_signal
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
from ta.volatility import AverageTrueRange

import csv
from datetime import datetime

def log_ml_data(symbol, direction, rsi, ema20, ema50, macd, volume_ratio, atr, market_trend, btc_strength, price_now):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    weekday = datetime.now().weekday()
    hour = datetime.now().hour

    try:
        with open("ml_log.csv", "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                now,
                symbol,
                direction,
                round(rsi, 2),
                round(ema20, 5),
                round(ema50, 5),
                round(macd, 5),
                round(volume_ratio, 3),
                round(atr, 5),
                market_trend,
                btc_strength,
                weekday,
                hour,
                price_now,
                "",  # Platzhalter für Preis in 5 Minuten
                "",  # Label (1/0) später berechnet
            ])
    except Exception as e:
        print(f"[ML_LOG] Fehler beim Schreiben in ml_log.csv: {e}", flush=True)



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

def log_trade(symbol, direction, entry_price, qty, tp, sl, callback_rate,
              rsi, ema20, ema50, macd_line, macd_signal,
              current_volume, avg_volume, market_trend, atr, btc_strength):

    filename = "trades.csv"
    file_exists = os.path.isfile(filename)

    with open(filename, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow([
                "timestamp", "symbol", "direction", "entry_price", "qty", "tp", "sl", "callback_rate",
                "rsi", "ema_diff", "macd_diff", "volume_ratio", "market_trend",
                "atr", "btc_strength", "weekday", "hour"
            ])

        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            symbol,
            direction,
            entry_price,
            qty,
            tp,
            sl,
            callback_rate,
            round(rsi, 2),
            round(ema20 - ema50, 5),
            round(macd_line - macd_signal, 5),
            round(current_volume / avg_volume, 3),
            market_trend,
            round(atr, 5),
            round(btc_strength, 3),
            datetime.now().weekday(),
            datetime.now().hour
        ])

import csv
from datetime import datetime
import os

def log_trade_result(symbol, direction, entry_price, result):
    file = "trade_log.csv"
    exists = os.path.exists(file)

    with open(file, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["Zeit", "Symbol", "Richtung", "Einstiegspreis", "Ergebnis"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            symbol,
            direction,
            round(entry_price, 4),
            result
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
        df = pd.DataFrame(res.json(), columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_volume', 'taker_buy_quote_volume', 'ignore'
        ])
        for c in ['open', 'high', 'low', 'close', 'volume']:
            df[c] = df[c].astype(float)
        return df
    except Exception as e:
        log_print(f"{symbol}: Fehler beim Laden: {e}")
        return None

        

def analyze_symbol(symbol, direction):
    df = get_klines(symbol, limit=50)
    if df is None or len(df) < 20:
        return None, ["Unzureichende Daten"]

    rsi = RSIIndicator(df['close'], window=14).rsi().iloc[-1]
    macd_line = MACD(df['close']).macd().iloc[-1]
    macd_signal = MACD(df['close']).macd_signal().iloc[-1]
    ema20 = EMAIndicator(df['close'], window=20).ema_indicator().iloc[-1]
    ema50 = EMAIndicator(df['close'], window=50).ema_indicator().iloc[-1]
    volume = df['volume'].iloc[-1]
    avg_volume = df['volume'].rolling(20).mean().iloc[-1]
    price = df['close'].iloc[-1]
    atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]

    # 🕯️ Candlestick-Analyse
    candle_size = df['close'].iloc[-1] - df['open'].iloc[-1]
    candle_direction = int(candle_size > 0)
    total_range = df['high'].iloc[-1] - df['low'].iloc[-1]
    candle_body_ratio = abs(df['close'].iloc[-1] - df['open'].iloc[-1]) / (total_range + 1e-6)

    # 🌎 Handels-Session basierend auf Uhrzeit
    current_hour = datetime.now().hour
    if 0 <= current_hour < 8:
        session = "Asia"
    elif 8 <= current_hour < 16:
        session = "Europe"
    elif 16 <= current_hour <= 23:
        session = "US"
    else:
        session = "Other"


    reasons = []

    # ML-Logging hier
    log_ml_data(
        symbol=symbol,
        direction=direction.upper(),
        rsi=rsi,
        ema20=ema20,
        ema50=ema50,
        macd=macd_line - macd_signal,
        volume_ratio=volume / avg_volume,
        atr=atr,
        market_trend="neutral",     # Oder echten Wert, wenn vorhanden
        btc_strength=0.5,           # Oder echten Wert, wenn vorhanden
        price_now=price
    )

    # Volumen-Filter
    if volume < 0.5 * avg_volume:
        reasons.append(f"Volumen zu gering ({volume:.2f} < {avg_volume:.2f})")
        return None, reasons

    # Long-Kriterien
    if direction == "long":
        if rsi > 33:
            reasons.append(f"RSI zu hoch für LONG ({rsi:.2f})")
        if ema20 <= ema50 * 0.998:
            reasons.append("EMA20 nicht über EMA50 (mit Spielraum) für LONG")
        if macd_line <= macd_signal:
            reasons.append("MACD gegen LONG")

        if len(reasons) == 1:
            log_missed_trade(
                symbol=symbol,
                direction="LONG",
                reasons=reasons,
                current_price=price,
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )

    if len(reasons) == 2:
        passed = []
        if rsi <= 33:
            passed.append("RSI ok")
        if ema20 > ema50 * 0.998:
            passed.append("EMA-Trend ok")
        if macd_line > macd_signal:
            passed.append("MACD ok")

        log_fast_signal(
            symbol=symbol,
            direction="LONG",
            passed=passed,
            failed=reasons,
            current_price=price,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    if reasons:
        return None, reasons

    trade_direction = "open_long"

    # Short-Kriterien
    if direction == "short":
        if rsi < 67:
            reasons.append(f"RSI zu niedrig für SHORT ({rsi:.2f})")
        if ema20 >= ema50 * 1.002:
            reasons.append("EMA20 nicht unter EMA50 (mit Spielraum) für SHORT")
        if macd_line >= macd_signal:
            reasons.append("MACD gegen SHORT")

    if len(reasons) == 1:
        log_missed_trade(
            symbol=symbol,
            direction="SHORT",
            reasons=reasons,
            current_price=price,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    if len(reasons) == 2:
        passed = []
        if rsi >= 67:
            passed.append("RSI ok")
        if ema20 < ema50 * 1.002:
            passed.append("EMA-Trend ok")
        if macd_line < macd_signal:
            passed.append("MACD ok")

        log_fast_signal(
            symbol=symbol,
            direction="SHORT",
            passed=passed,
            failed=reasons,
            current_price=price,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    if reasons:
        return None, reasons

    trade_direction = "open_short"

    # 📌 TP/SL berechnen
    if trade_direction == "open_long":
        tp = price + 1.5 * atr
        sl = price - 0.9 * atr
    else:
        tp = price - 1.5 * atr
        sl = price + 0.9 * atr

    qty = round(START_CAPITAL / price, 3)

    features = {
        "rsi": rsi,
        "ema_diff": ema20 - ema50,
        "macd_abs": abs(macd_line - macd_signal),
        "volume_ratio": volume / avg_volume if avg_volume > 0 else 1,
        "atr": atr,
        "btc_strength": 0.0,
        "weekday": datetime.now().weekday(),
        "hour": datetime.now().hour,
        "candle_direction": candle_direction,
        "candle_body_ratio": candle_body_ratio,
        "session_asia": 1 if session == "Asia" else 0,
        "session_europe": 1 if session == "Europe" else 0,
        "session_us": 1 if session == "US" else 0
    }


    ml_prediction, ml_prob = predict_signal(features)

    # ✏️ Nachricht bauen
    msg = (f"📢 *Signal {trade_direction} für {symbol}*\n"
           f"RSI: {rsi:.2f}, EMA20/EMA50: {ema20:.2f}/{ema50:.2f}\n"
           f"TP: {tp:.4f} | SL: {sl:.4f}\n"
           f"🤖 ML: {'JA' if ml_prediction else 'NEIN'} ({ml_prob:.2f})")

    # 🔁 Rückgabe
    return {
        "direction": trade_direction,
        "qty": qty,
        "tp": tp,
        "sl": sl,
        "msg": msg,
        "rsi": rsi,
        "ema20": ema20,
        "ema50": ema50,
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "volume": volume,
        "avg_volume": avg_volume,
        "atr": atr,
        "btc_strength": btc_strength
    }, []




def round_to_step(value, step):
    """
    Rundet einen Wert sauber auf die zulässige Schrittgröße (Tickgröße oder Stückelung).
    Beispiel: 0.07631 bei Schritt 0.01 → 0.07
    """
    d_value = Decimal(str(value))
    d_step = Decimal(str(step))
    return float((d_value // d_step) * d_step)

    

def place_order(symbol, direction, quantity, tp, sl,
                rsi, ema20, ema50, macd_line, macd_signal,
                current_volume, avg_volume, market_trend, atr, btc_strength):
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
            try:
                price = float(order.get('avgFillPrice') or order.get('price') or order['fills'][0]['price'])
            except Exception as e:
                log_print(f"{symbol}: ❌ Kein Preis in Orderantwort: {e}")
                continue  # ➤ versuche den nächsten attempt


            capital_lost += potenzieller_verlust
            log_print(f"{symbol}: ✅ Order {side} {quantity} erfolgreich")
            log_print(f"{symbol}: 📉 Kumulierter Verlust: {capital_lost:.2f} USDT")

            log_trade(
                symbol, direction, price, quantity, tp, sl, 0.0,
                rsi, ema20, ema50, macd_line, macd_signal,
                current_volume, avg_volume, market_trend, atr, btc_strength
            )



            sl_order_type = "STOP_MARKET"
            sl_side = "SELL" if direction == "LONG" else "BUY"
            position_side = "LONG" if direction == "LONG" else "SHORT"

            # ✅ Fester TP (Limit-Order)
            try:
                client.new_order(
                    symbol=symbol,
                    side=sl_side,  # SELL bei LONG, BUY bei SHORT
                    positionSide=position_side,
                    type="LIMIT",
                    price=round(tp, 4),
                    quantity=quantity,
                    timeInForce="GTC",
                    reduceOnly=True
                )
                log_print(f"{symbol}: ✅ TP gesetzt bei {tp:.4f}")
            except Exception as e:
                log_print(f"{symbol}: ❌ Fehler beim Setzen des TP: {e}")


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

def update_future_prices():
    import pandas as pd
    from datetime import datetime, timedelta

    file = "ml_log.csv"

    try:
        columns = [
            "timestamp", "symbol", "direction", "rsi", "ema20", "ema50", "macd",
            "volume_ratio", "atr", "market_trend", "btc_strength",
            "weekday", "hour", "price_now", "future_price", "label"
        ]
        df = pd.read_csv(file, names=columns, header=None)

    except Exception as e:
        log_print(f"❌ Fehler beim Laden von ml_log.csv: {e}")
        return

    updated = 0

    for i, row in df.iterrows():
        try:
            if pd.isna(row["future_price"]) and not pd.isna(row["timestamp"]):
                timestamp_str = row["timestamp"]
                symbol = row["symbol"]
                ts = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                if datetime.now() >= ts + timedelta(minutes=5):
                    df_klines = get_klines(symbol, interval="1m", limit=2)
                    if df_klines is not None and not df_klines.empty:
                        future_price = df_klines['close'].iloc[-1]
                        df.at[i, "future_price"] = round(future_price, 5)
                        updated += 1
                        log_print(f"🔁 Nachgetragen: {symbol} → future_price = {future_price}")
        except Exception as e:
            log_print(f"⚠️ Fehler bei Zeile {i}: {e}")
            continue

    if updated > 0:
        try:
            df.to_csv(file, index=False)
            log_print(f"✅ {updated} future_price-Werte gespeichert.")
        except Exception as e:
            log_print(f"❌ Fehler beim Speichern von ml_log.csv: {e}")
    else:
        log_print("ℹ️ Keine neuen future_price-Einträge nötig.")

def monitor_trades():
    try:
        positions = client.get_position_risk()
    except Exception as e:
        log_print(f"❌ Fehler beim Abrufen der offenen Positionen: {e}")
        return

    for pos in positions:
        symbol = pos['symbol']
        amt = float(pos['positionAmt'])
        entry_price = float(pos['entryPrice'])

        # Keine Position → wurde also geschlossen
        if amt == 0.0 and entry_price > 0:
            # Richtung bestimmen (Binance speichert Einträge trotzdem mit entry_price)
            side = "LONG" if float(pos['positionSide']) == 1 else "SHORT"

            # Ergebnis schätzen – TP oder SL
            mark_price = float(pos['markPrice'])
            result = "TP" if (
                (side == "LONG" and mark_price > entry_price)
                or (side == "SHORT" and mark_price < entry_price)
            ) else "SL"

            log_trade_result(symbol, side, entry_price, result)
            log_print(f"{symbol}: 📋 Trade abgeschlossen ({side}) – {result}")





def run_bot():
    log_print("🚀 run_bot gestartet")
    log_print("📊 Starte neue Analyse...")

    try:
        info = client.exchange_info()
    except Exception as e:
        log_print(f"❌ exchange_info-Fehler: {e}")
        return

    try:
        excluded_symbols = ["USDCUSDT", "TUSDUSDT", "DAIUSDT", "FDUSDUSDT", "BUSDUSDT", "USDPUSDT"]
        symbols = [s['symbol'] for s in info['symbols']
                   if s['contractType'] == "PERPETUAL"
                   and s['quoteAsset'] == "USDT"
                   and s['status'] == "TRADING"
                   and s['symbol'] not in excluded_symbols]

        log_print(f"✅ {len(symbols)} Symbole geladen")

        market_trend = get_market_trend(client, symbols)
        log_print(f"⬆️ Markttrend erkannt: {market_trend.upper()}")

        analyzed = signals = orders = 0
        for sym in symbols:
            try:
                for direction in ["long", "short"]:
                    log_print(f"{sym}: 🔍 Analyse für {direction.upper()}")
                    res, reasons = analyze_symbol(sym, direction)
                    analyzed += 1

                    if res is None and "Unzureichende Daten" in reasons:
                        log_ml_data(
                            symbol=symbol,
                            direction=direction.upper(),
                            rsi=rsi,
                            ema20=ema20,
                            ema50=ema50,
                            macd=macd_line - macd_signal,
                            volume_ratio=volume / avg_volume,
                            atr=atr,
                            market_trend="neutral",     # Optional: später mit echten Werten
                            btc_strength=0.5,           # Optional: später dynamisch
                            price_now=price,
                            candle_size=candle_size,
                            candle_direction=candle_direction,
                            candle_body_ratio=candle_body_ratio,
                            session=session
                        )


                    if res is None:
                        grund = ', '.join(reasons)
                        log_print(f"{sym}: ❌ Kein gültiges {direction.upper()}-Signal – Gründe: {grund}")
                        continue

                    if res["direction"] == "open_long" and market_trend == "strong_bearish":
                        log_print(f"{sym}: ⛔️ LONG blockiert durch starken Bärenmarkt")
                        continue
                    if res["direction"] == "open_short" and market_trend == "strong_bullish":
                        log_print(f"{sym}: ⛔️ SHORT blockiert durch starken Bullenmarkt")
                        continue

                    send_telegram(res["msg"])
                    signals += 1

                    if bot_active:
                        place_order(
                            sym,
                            res["direction"],
                            res["qty"],
                            res["tp"],
                            res["sl"],
                            res["rsi"],
                            res["ema20"],
                            res["ema50"],
                            res["macd_line"],
                            res["macd_signal"],
                            res["volume"],
                            res["avg_volume"],
                            market_trend,
                            res["atr"],
                            res["btc_strength"]
                        )
                        orders += 1
                    else:
                        log_print(f"{sym}: 🔒 Bot nicht aktiv – keine Order trotz gültigem Signal.")

            except Exception as e:
                log_print(f"{sym}: ❌ Analyse-Fehler: {e}")

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

def log_fast_signal(symbol, direction, passed, failed, current_price, timestamp):
    import os
    import csv

    filename = 'fast_signals.csv'
    headers = ['timestamp', 'symbol', 'direction', 'current_price', 'passed_criteria', 'failed_criteria']

    row = {
        'timestamp': timestamp,
        'symbol': symbol,
        'direction': direction,
        'current_price': current_price,
        'passed_criteria': '; '.join(passed),
        'failed_criteria': '; '.join(failed)
    }

    file_exists = os.path.isfile(filename)
    with open(filename, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

def log_missed_trade(symbol, direction, reasons, current_price, timestamp):
    import os
    import csv

    filename = 'missed_signals.csv'
    headers = ['timestamp', 'symbol', 'direction', 'current_price', 'reasons']

    row = {
        'timestamp': timestamp,
        'symbol': symbol,
        'direction': direction,
        'current_price': current_price,
        'reasons': '; '.join(reasons)
    }

    file_exists = os.path.isfile(filename)
    with open(filename, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


if __name__ == "__main__":
    send_telegram("🚀 Bot manuell gestartet (Live-Modus)")

    # 🧪 Test-Trade (nur einmal starten, danach wieder auskommentieren oder löschen)
    #place_order("BTCUSDT", "LONG", 0.001, 70000, 68000)

    # Starte Bot direkt
    run_bot()

    # Wiederhole alle 1 Minuten
    schedule.every(1).minutes.do(run_bot)
    schedule.every(5).minutes.do(update_future_prices)
    schedule.every(1).minutes.do(monitor_trades)

    # Starte Schleife sichtbar im Terminal
    while True:
        schedule.run_pending()
        time.sleep(1)



