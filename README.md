# Linksignal Bot

Dieser Bot prüft alle 5 Minuten den RSI von LINKUSDT über Binance API und sendet ein Telegram-Signal, wenn RSI < 30 (LONG) oder > 70 (SHORT) ist.

## Telegram Setup
- Erstelle einen Bot über @BotFather
- Starte den Chat mit deinem Bot und hole deine `chat_id` über eine Anfrage oder Bot-Log
- Füge `TELEGRAM_TOKEN` und `CHAT_ID` als Environment-Variablen bei Render hinzu

## Deployment
1. Code auf GitHub hochladen
2. Bei render.com neuen Web Service anlegen
3. Python Version: 3.11
4. `main.py` ist Entry Point
5. Environment Variables:
   - `TELEGRAM_TOKEN`
   - `CHAT_ID`
