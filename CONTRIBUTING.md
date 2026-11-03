# Mitwirken

1. Repository klonen und eine eigene virtuelle Python-Umgebung erstellen.
2. `python -m pip install -r requirements-dev.txt`
3. `python -m unittest test_server -v` ausführen.
4. Änderungen mit passenden Offline-Tests als Pull Request einreichen.

Node.js 24 wird für den optionalen Referenzdecoder-Test verwendet.
CI prüft Python 3.12–3.14 auf macOS, Linux und Windows, ohne Bluetooth-Hardware.
Ein bestandener CI-Lauf bestätigt keine Hardwarekompatibilität.

Keine `.env`, Zugriffsschlüssel, Zertifikate, Bluetooth-Adressen oder personenbezogenen
Druckinhalte einchecken. Für Hardwareberichte Modell/Firmware, Betriebssystem und
anonymisierte Fehlermeldung angeben. Nach einem Timeout niemals blind erneut drucken.

Protokolländerungen mit Quellen, Testdaten und verbleibenden Unsicherheiten dokumentieren.
Die MIT-Lizenz und Hinweise in `reference/` erhalten.
