# Multicoin Signal Bot (RSI + MACD + EMA)

Analysiert alle 5 Minuten mehrere Coins:
- LINK, ENA, MOVE, ONDO, XRP, ETH

### Signalbedingungen:
- RSI < 30, MACD-Diff > 0, Preis > EMA20 → LONG
- RSI > 70, MACD-Diff < 0, Preis < EMA20 → SHORT

Telegram-Nachricht wird bei Signal automatisch gesendet.
