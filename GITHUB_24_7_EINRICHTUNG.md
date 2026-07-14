# Kostenlose 24/7-Einrichtung mit GitHub Actions

Der Bot läuft in einem öffentlichen GitHub-Repository auch bei ausgeschaltetem PC. Die Gmail-Zugangsdaten werden ausschließlich als geschützte Repository-Secrets gespeichert.

## 1. Neues Repository

1. Auf GitHub oben rechts auf **+ → New repository** klicken.
2. Name: `midea-knuffelwuff-bot-neu`.
3. **Public** wählen.
4. README, `.gitignore` und Lizenz **nicht** vorab anlegen.
5. **Create repository** anklicken.

## 2. Dateien korrekt hochladen

1. ZIP entpacken und den Ordner `midea-stock-bot` öffnen.
2. Prüfen, dass dort der Ordner `.github` neben `bot.py` liegt.
3. Alle Inhalte in diesem Ordner markieren, einschließlich `.github`.
4. Im leeren GitHub-Repository **uploading an existing file** bzw. **Add file → Upload files** öffnen.
5. Die markierten Inhalte in das Upload-Feld ziehen.
6. Nicht den Ordner `midea-stock-bot` selbst als zusätzlichen Unterordner hochladen.
7. **Commit changes** anklicken.

Richtige Struktur:

```text
.github/
  workflows/
    check-stock.yml
    email-test.yml
    keepalive.yml
bot.py
config.toml
requirements.txt
```

## 3. Nur drei Secrets anlegen

Im Repository **Settings → Secrets and variables → Actions → New repository secret** öffnen und diese drei Secrets einzeln anlegen:

| Name | Wert |
|---|---|
| `SMTP_USERNAME` | vollständige Gmail-Adresse |
| `SMTP_PASSWORD` | 16-stelliges Google-App-Passwort ohne Leerzeichen |
| `EMAIL_TO` | gewünschte Empfängeradresse |

Das normale Google-Passwort darf nicht verwendet werden. Niemals ein Passwort in eine Repository-Datei schreiben.

## 4. Schreibberechtigung

Unter **Settings → Actions → General → Workflow permissions** die Option **Read and write permissions** wählen und speichern. Dies wird nur vom monatlichen Keepalive-Workflow benötigt.

## 5. Testmail

1. Oben **Actions** öffnen.
2. Links **E-Mail testen** anklicken.
3. Rechts **Run workflow → Run workflow** anklicken.
4. Den Lauf öffnen und auf grüne Häkchen warten.

## 6. Bot starten

1. Unter **Actions** links **Midea und Knuffelwuff prüfen** öffnen.
2. **Run workflow → Run workflow** anklicken.
3. Der erste Knuffelwuff-Lauf speichert nur die Ausgangsliste.

Danach läuft der Bot automatisch ungefähr alle 15 Minuten.
