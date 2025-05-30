# train_model.py
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

# === Spaltennamen exakt an CSV-Datei anpassen ===
#columns = [
    #"timestamp", "symbol", "direction", "score", "entry_price", "current_price", "price_diff",
    #"btc_strength", "atr", "market_phase", "rsi", "macd", "ema20", "ema50",
    #"volume_ratio", "future_price"
#]

columns = [
  "timestamp", "symbol", "direction", "rsi", "ema20", "ema50", "macd", "volume_ratio",
  "atr", "market_trend", "btc_strength", "weekday", "hour", "price_now", "future_price", "label"
]

df = pd.read_csv("ml_log.csv", header=None, names=columns)

print(df.head(3).to_string())
print(f"🔢 Ursprüngliche Zeilen: {len(df)}")

# === Spalten in float konvertieren ===
cols_to_float = [
    "rsi", "ema20", "ema50", "macd", "volume_ratio",
    "atr", "btc_strength", "future_price"
]
for col in cols_to_float:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# === Timestamp-Spalten konvertieren ===
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df["weekday"] = df["timestamp"].dt.weekday
df["hour"] = df["timestamp"].dt.hour

# === Nur Zeilen mit gültigen future_price verwenden ===
df = df[df["future_price"].notna()]

# === Label-Berechnung mit current_price (anstatt price_now) ===
def calculate_label(row):
    if row["direction"] == "LONG" and row["future_price"] >= row["price_now"] * 1.002:              #"current_price" stand 29.05 15:00
        return 1
    elif row["direction"] == "SHORT" and row["future_price"] <= row["price_now"] * 0.998:           #"current_price" stand 29.05 15:00
        return 1
    else:
        return 0

df["label"] = df.apply(calculate_label, axis=1)

import os

# === NaNs entfernen ===
df.dropna(inplace=True)
print(f"🩼 Nach dropna(): {len(df)}")

if len(df) == 0:
    print("❌ Fehler: Keine Daten nach dropna(). Möglicherweise falsche oder leere ml_log.csv geladen.")
    print("📂 Geladener Pfad:", os.path.abspath("ml_log.csv"))
    print("📄 Vorschau auf letzte 3 Zeilen der Datei:")
    raw = pd.read_csv("ml_log.csv", header=None)
    print(raw.tail(3).to_string())
    exit()

print(f"🏷️ Final für Training verwendbare Zeilen: {len(df)}")

# === Feature-Engineering ===
df["ema_diff"] = df["ema20"] - df["ema50"]
df["macd_abs"] = df["macd"].abs()


X = df[[  # exakt dieselben 8 Features wie im ml_predict.py
    "rsi", "ema_diff", "macd_abs", "volume_ratio",
    "atr", "btc_strength", "weekday", "hour"
]]
y = df["label"]


# === Skalierung & Split ===
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# === Modell trainieren ===
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train_scaled, y_train)

# === Modell & Scaler speichern ===
joblib.dump(model, "ml_model.pkl")
joblib.dump(scaler, "ml_scaler.pkl")

# === Evaluation ===
y_pred = model.predict(X_test_scaled)
print(classification_report(y_test, y_pred))



