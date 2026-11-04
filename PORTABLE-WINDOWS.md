# Portable Windows-Version

Das **portable Paket** enthält eine offizielle eingebettete CPython-3.14.7-Laufzeit
und Windows-x64-Abhängigkeiten. Der normale GitHub-Quellcode-Download enthält diese
Laufzeit nicht!

## Download

Öffne [Portable Windows ZIP – Builds](https://github.com/schruptor/e10-print-server/actions/workflows/portable-windows.yml),
wähle einen erfolgreichen Lauf und lade unter **Artifacts** das Artefakt
**e10-portable-windows-x64** herunter. Dafür sind GitHub-Anmeldung und Zugriff
auf das Repository erforderlich.

Entpacke das Artefakt: Darin liegen das portable ZIP und seine SHA-256-Datei.
Das innere ZIP kann ohne GitHub-Zugang an den Empfänger weitergegeben werden.
Artefakte werden 30 Tage aufbewahrt; bereits heruntergeladene Pakete bleiben nutzbar.

Der erste Build wurde erfolgreich auf einem Windows-GitHub-Runner geprüft:
Laufzeit-Imports, Textdarstellung und HTTP-Serverstart. Bluetooth-Hardwaredruck
auf dem Ziel-PC bleibt ungetestet.

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
