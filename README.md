# Midea PortaSplit + Knuffelwuff Bot – kostenlose E-Mail-Version

Dieser Bot läuft kostenlos auf deinem Windows-PC und überwacht:

- Midea PortaSplit bei OBI, toom, Lidl und Amazon
- das Knuffelwuff-Sortiment in den Hauptkategorien

Der Bot sendet eine E-Mail, wenn:

- eine Midea PortaSplit wieder verfügbar wird,
- ein neuer, lieferbarer Knuffelwuff-Artikel erscheint,
- ein zuvor nicht lieferbarer Knuffelwuff-Artikel wieder lieferbar ist.

## Wichtig beim ersten Knuffelwuff-Lauf

Beim ersten Lauf speichert der Bot den aktuellen Knuffelwuff-Bestand als Ausgangsbasis. Er sendet dabei absichtlich keine E-Mails für alle bereits vorhandenen Produkte. Erst spätere echte Änderungen lösen eine Nachricht aus.

## Prüfintervall

Der Bot prüft standardmäßig alle **15 Minuten**. Die Einstellung steht in `config.toml`:

```toml
[settings]
check_interval_minutes = 15
```

Ein Intervall unter 10 Minuten wird vom Programm verhindert, um die Shops nicht unnötig zu belasten.

## Installation unter Windows

1. ZIP-Datei vollständig entpacken.
2. `1_installieren_windows.bat` doppelklicken.
3. E-Mail-Zugangsdaten über `2_email_einstellungen_oeffnen_windows.bat` eintragen.
4. Mit `2_email_testen_windows.bat` die normale E-Mail testen.
5. Mit `6_knuffelwuff_test_windows.bat` eine Knuffelwuff-Testmail senden.
6. Mit `7_einmal_pruefen_ohne_mail_windows.bat` eine Prüfung ohne E-Mail-Versand durchführen.
7. Mit `3_bot_starten_windows.bat` den Dauerbetrieb starten.

Für den Autostart nach der Windows-Anmeldung kann anschließend `4_autostart_einrichten_windows.bat` verwendet werden.

## Aktualisierung eines bereits eingerichteten Bots

Wenn dein alter Bot bereits eine funktionierende `.env`-Datei enthält:

1. Alten Bot mit `Strg+C` beenden.
2. Die Dateien aus dem Update-ZIP direkt in den vorhandenen `midea-stock-bot`-Ordner kopieren.
3. Bei der Windows-Frage **„Dateien ersetzen?“** auf **„Ja“** klicken.
4. Die vorhandene `.env` und `state.json` nicht löschen.
5. `7_einmal_pruefen_ohne_mail_windows.bat` starten.
6. Danach `3_bot_starten_windows.bat` starten.

Eine erneute Python-Installation ist beim Update normalerweise nicht erforderlich.

## Gmail-Konfiguration

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=dein.bot.konto@gmail.com
SMTP_PASSWORD=DEIN_16_STELLIGES_APP_PASSWORT
EMAIL_FROM=dein.bot.konto@gmail.com
EMAIL_TO=DEINE_EMPFAENGERADRESSE
SMTP_STARTTLS=true
SMTP_SSL=false
```

Für `SMTP_PASSWORD` muss ein Google-App-Passwort verwendet werden, nicht das normale Google-Passwort.

## Knuffelwuff-Kategorien

Der Bot prüft die Kategorien:

- Schlafplatz
- Reise & Transport
- Hundefutter
- Bekleidung
- Leinen & Halsbänder
- Spielzeug
- Outlet

Die Kategorien stehen im Abschnitt `[[catalogs]]` der Datei `config.toml`.

## Dateien

- `3_bot_starten_windows.bat`: Dauerbetrieb
- `6_knuffelwuff_test_windows.bat`: Testmail für Knuffelwuff
- `7_einmal_pruefen_ohne_mail_windows.bat`: einmalige Diagnose ohne Mail
- `bot.log`: Protokoll beim unsichtbaren Autostart
- `state.json`: gespeicherter letzter Zustand
- `.env`: private E-Mail-Zugangsdaten

## Sicherheit und Grenzen

- Keine kostenpflichtigen Bot-Dienste und keine WhatsApp-API
- Keine Captcha-Umgehung und kein Shop-Login
- Der PC muss eingeschaltet und mit dem Internet verbunden sein
- Shop-Seiten können ihr Layout ändern; dann können Anpassungen erforderlich werden
- `.env` niemals weitergeben oder öffentlich hochladen

## 24/7-Betrieb ohne eingeschalteten PC

Für den kostenlosen Dauerbetrieb ist eine vorbereitete GitHub-Actions-Konfiguration enthalten. Die vollständige Klick-für-Klick-Anleitung steht in:

`GITHUB_24_7_EINRICHTUNG.md`

Der GitHub-Workflow prüft automatisch ungefähr alle 15 Minuten. Für dauerhaft kostenlose Nutzung sollte das Repository öffentlich sein; E-Mail-Passwörter werden ausschließlich als GitHub-Secrets gespeichert und dürfen niemals als `.env` hochgeladen werden.
