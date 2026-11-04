# Portable Windows-Version

Das **portable Paket** enthält eine offizielle eingebettete CPython-3.14.7-Laufzeit
und Windows-x64-Abhängigkeiten. Der normale GitHub-Quellcode-Download enthält diese
Laufzeit nicht!

## Für Empfänger

1. `e10-print-server-portable-windows-x64.zip` vollständig entpacken.
2. In einen beschreibbaren Ordner legen; nicht direkt aus der ZIP starten.
3. `start.cmd` doppelklicken.
4. Falls nötig `http://127.0.0.1:1312` im Browser öffnen.
5. Bluetooth aktivieren, E10 suchen und verbinden.

Keine vorherige Python-Installation, kein pip und kein Internetdownload beim Start.
Windows 11 x64 (Intel/AMD) mit funktionsfähigem Bluetooth-LE-Adapter erforderlich.
Keine native ARM64-Ausgabe. Keine Firewallregeln oder Autostarts werden angelegt.

`restart.cmd` startet neu, `stop.cmd` beendet die verwaltete Instanz.
Nur zwischen Druckaufträgen verwenden. Einstellungen bleiben in `.env`;
Logs stehen in `.runtime`. Endlosband verwenden und Handy-Verbindung trennen.

Der Ordner bleibt nach dem Entpacken verschiebbar, aber nur bei gestopptem Server.
Keine Anmeldung: nur lokal oder im vertrauenswürdigen LAN einsetzen.

## Build

GitHub Actions → **Portable Windows ZIP** → **Run workflow**.
Das Ergebnis liegt als Workflow-Artefakt vor (30 Tage Aufbewahrung).
Im Artefakt befinden sich das weiterzugebende ZIP und dessen SHA-256-Datei.
Nur dieses innere ZIP an den Empfänger weitergeben.

Der Build läuft auf Windows. Er prüft die eingebettete Laufzeit, Windows-Bluetooth-
Imports, Textdarstellung und einen echten lokalen HTTP-Serverstart. Das ersetzt
keinen Bluetooth-/Drucktest an einem echten E10 und keinen Test aller Windows-PCs.

Abhängigkeiten werden beim Build aus PyPI installiert und als Anwendungsteil
mitgeliefert; Paketmetadaten/Lizenzen bleiben enthalten. Python stammt von python.org.
Version, Quelladresse, Laufzeit-Prüfsumme und Commit stehen im Paket in BUILD-INFO.json.
Neue Builds können innerhalb der Grenzen von requirements.txt neuere Bibliotheken erhalten.
