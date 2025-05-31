# Verwende eine offizielle Python-Umgebung
FROM python:3.10-slim

# Setze das Arbeitsverzeichnis
WORKDIR /app

# Kopiere den Code ins Image
COPY . .

# Installiere Abhängigkeiten
RUN pip install --upgrade pip && pip install -r requirements.txt

# Starte den Bot
CMD ["python", "main.py"]
