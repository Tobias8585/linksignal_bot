# ml_predict.py
import pandas as pd
import joblib
from datetime import datetime

def predict_signal():
    # Die Datei einlesen mit den richtigen Spaltennamen
    columns = [
        "timestamp", "symbol", "direction", "rsi", "ema20", "ema50", "macd", "volume_ratio",
        "atr", "market_trend", "btc_strength", "weekday", "hour", "price_now", "future_price", "label"
    ]
    df = pd.read_csv("ml_log.csv", header=None, names=columns)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    # Nur die letzte Zeile verwenden
    last = df.tail(1).copy()

    # Feature-Engineering exakt wie im train_model.py
    last["ema_diff"] = last["ema20"] - last["ema50"]
    last["macd_abs"] = last["macd"].abs()

    # Features auswählen
    features = last[[
        "rsi", "ema_diff", "macd_abs", "volume_ratio",
        "atr", "btc_strength", "weekday", "hour"
    ]]

    # Modell & Scaler laden
    model = joblib.load("ml_model.pkl")
    scaler = joblib.load("ml_scaler.pkl")

    # Skalieren und Vorhersage
    features_scaled = scaler.transform(features)
    prediction = model.predict(features_scaled)
    proba = model.predict_proba(features_scaled)

    return prediction[0], proba[0][1]

if __name__ == "__main__":
    pred, prob = predict_signal()
    print("📊 Vorhersage:", "✅ GUTER TRADE" if pred == 1 else "❌ Kein guter Trade")
    print(f"🔢 Wahrscheinlichkeit für Erfolg (Label=1): {prob:.2%}")
