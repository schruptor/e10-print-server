# E10 Textdruck-Server

Experimenteller Python-Port für E10/T15 über Bluetooth LE. Eine Python-Datei enthält Weboberfläche,
HTTP-API und Treiber. Keine Cloud, kein Node.js für den Betrieb. Unterstütztes Ziel: macOS, Linux,
Windows mit einem funktionierenden Bluetooth-LE-Adapter. Tatsächlich eingerichtet und offline getestet
wurde bisher nur der Mac; Hardware-Druck und andere Betriebssysteme sind noch nicht bestätigt.

## Schnellstart

```sh
git clone https://github.com/schruptor/e10-print-server.git
cd e10-print-server
```

Anschließend die Installation für das eigene Betriebssystem weiter unten ausführen.
Die lokale `.env` wird nicht mitgeliefert: `.env.example` kopieren.
Es gibt keine Anmeldung. Jeder mit Netzwerkzugriff auf den Server kann drucken.

## Funktionen

- Browseroberfläche mit Druckerauswahl, Text, Länge, Dichte und Kopien.
- Immer sichtbare Live-Vorschau: aktualisiert sich beim Einfügen/Tippen und bei jeder Einstellungsänderung (200 ms nach der letzten Eingabe).
- Kopien als separate Druckaufträge: erst Druckabschluss abwarten, dann fünf Sekunden Schneidepause mit Countdown, danach die nächste Kopie. Keine Pause nach der letzten Kopie.
- Die Vorschau zeigt ein Etikett; Dichte beeinflusst die Druckwärme, nicht die Bildschirmdarstellung. Kopienzahl und Pausen werden daneben angezeigt.
- Leerer Text zeigt ein leeres Etikett in der Vorschau, kann aber nicht gedruckt werden.
- Bluetooth läuft auf dem Serverrechner; Bedienung im LAN auch vom iPhone möglich.
- Konfigurierbare Bind-IP, Port, HTTP/HTTPS und PEM-Zertifikatspfade.
- Ein Python-Einstiegspunkt; keine Cloud und kein Node.js im Produktivbetrieb.

## Lokaler Start nach der Installation

```sh
cd ~/e10-print-server
.venv/bin/python e10_server.py
```

Dann http://127.0.0.1:8080 öffnen. Kein Zugriffsschlüssel erforderlich.
E10 einschalten, gegebenenfalls Verbindung der iPhone-App trennen, **Drucker suchen**,
den eigenen E10 (oft T0… als Bluetooth-Name) auswählen und **Verbinden**.
Die Liste enthält auch ähnliche Supvan-Geräte: nur den eigenen E10 auswählen.
Die erfolgreiche Auswahl wird lokal in `printer.json` gespeichert; nach Neustart explizit verbinden.
Text eingeben, Länge passend zum eingelegten Band wählen, Vorschau prüfen, mit einer Kopie testen.
Die maximale Textfläche ist 88 Punkte hoch, zentriert auf dem 96-Punkte-Druckkopf.

Die Oberfläche löst keine Druckvorgänge beim Laden aus. Erst der Druckknopf sendet einen Auftrag.
Bei einem Timeout kann ein Teil bereits gedruckt sein: Gerät prüfen, nicht blind wiederholen.

## Installation auf einem anderen Rechner

Empfehlung: CPython 3.12–3.14; auf diesem Mac ist die isolierte Umgebung Python 3.14.
Projektdateien kopieren, aber `.venv` nie zwischen Betriebssystemen kopieren.

macOS/Linux:
```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python e10_server.py
```

### Windows: Installation und Verwaltung per Doppelklick

Voraussetzungen: Windows 11 mit Bluetooth LE und installiertes **CPython 3.12–3.14**
(inklusive Python-Launcher oder `python` im PATH). Der Installer installiert Python
nicht selbst. Projekt in einen beschreibbaren Ordner entpacken, zum Beispiel
`C:\Users\Name\Apps\e10-print-server`. Keine Mac-/Linux-`.venv` mitkopieren.

| Datei | Funktion |
| --- | --- |
| `install.cmd` | Erstellt die virtuelle Umgebung, lädt Python-Abhängigkeiten und legt eine fehlende `.env` an. |
| `start.cmd` | Startet den Server im Hintergrund und öffnet die konfigurierte URL im Browser. |
| `restart.cmd` | Stoppt die verwaltete Instanz und startet sie mit aktuellen Einstellungen neu. |
| `stop.cmd` | Beendet ausschließlich die durch diese Skripte verwaltete Instanz. |

Zuerst **install.cmd**, dann **start.cmd** doppelklicken. Alternativ in PowerShell:

```powershell
.\install.cmd
.\start.cmd
# Spaeter:
.\restart.cmd
.\stop.cmd
```

Vorhandene `.env` und Druckerauswahl bleiben erhalten. Keine Administratorrechte
oder dauerhafte Änderung der PowerShell-Ausführungsrichtlinie erforderlich.
Installation benötigt Internet; es werden keine Firewallregeln oder Autostarts angelegt.
Die CMD-Dateien starten Windows PowerShell mit einer nur für diesen Aufruf geltenden
`ExecutionPolicy Bypass`; zentral verwaltete Richtlinien können das weiterhin verhindern.

Logs und Prozesskennung: `.runtime/stdout.log`, `.runtime/stderr.log` und
`.runtime/server.json`. Logs werden bei jedem Start neu geschrieben.
Ein belegter Port wird nicht freigeräumt; manuell gestartete Server zuerst manuell stoppen.
**Stopp/Neustart nur zwischen Druckaufträgen:** Windows beendet den Prozess unmittelbar,
ein laufender Druck könnte unvollständig bleiben. Danach Drucker erneut verbinden.

Die Windows-Skripte sind auf dem Mac erstellt, aber noch nicht unter Windows ausgeführt.
Die folgende manuelle Installation bleibt als Alternative verfügbar.

Windows PowerShell (manuell):
```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe e10_server.py
```

Bluetooth-Voraussetzungen laut Bleak: macOS 10.15+, Linux mit BlueZ >= 5.55,
Windows 11 ab Build 22000 (aktuelle Bleak-3-Dokumentation).
Linux benötigt einen laufenden BlueZ-Dienst, D-Bus-Zugang und passende Benutzerrechte.
Unter macOS die Bluetooth-Abfrage für Terminal/Python erlauben; unter Windows ggf. Firewall-Freigabe
für LAN-Zugriff. Nicht pauschal als root/Administrator starten.
Siehe https://bleak.readthedocs.io/en/latest/ .

## .env-Konfiguration

```dotenv
SERVER_IP=127.0.0.1
SERVER_PORT=8080
SERVER_SCHEME=http
SSL_CERT_FILE=
SSL_KEY_FILE=
SSL_KEY_PASSWORD=
FONT_PATH=
```

- `SERVER_IP`: Bind-Adresse, nicht die URL. `127.0.0.1` nur lokal;
  `0.0.0.0` bindet alle IPv4-Interfaces, alternativ die konkrete LAN-IP des Rechners.
- `SERVER_PORT`: 1–65535.
- `SERVER_SCHEME`: `http` oder `https`. Bei HTTPS sind Zertifikat und Schlüssel Pflicht;
  bei Fehlern gibt es keinen stillen Rückfall auf HTTP.
- `SSL_CERT_FILE`: PEM-Zertifikat/Fullchain; `SSL_KEY_FILE`: passender PEM-Privatschlüssel.
- `SSL_KEY_PASSWORD`: optional für verschlüsselten privaten Schlüssel.
- `FONT_PATH`: optional eine TTF/OTF-Schrift, die auf diesem Rechner vorhanden ist.
  Ohne Vorgabe werden Arial (Mac/Windows), DejaVu Sans (Linux) und zuletzt Pillow-Fallback probiert.
  Emojis/komplexe Schriften sind nicht garantiert; Vorschau prüfen.
- Relative Dateipfade beziehen sich auf den Projektordner, auch wenn von woanders gestartet wird.
  Windows-Beispiel: `SSL_CERT_FILE=C:/certs/e10/fullchain.pem`.
- Bereits gesetzte Prozess-Umgebungsvariablen haben Vorrang vor `.env`.
- Konfigurationsänderungen benötigen einen Neustart.

HTTPS-Beispiel:
```dotenv
SERVER_IP=0.0.0.0
SERVER_PORT=8443
SERVER_SCHEME=https
SSL_CERT_FILE=certs/fullchain.pem
SSL_KEY_FILE=certs/privkey.pem
```

Eigene Zertifikate bereitstellen; es wird keine CA installiert und kein Zertifikat automatisch erzeugt.
Der Hostname/die IP in der aufgerufenen URL muss zum Zertifikat passen, dessen CA muss auf dem
aufrufenden Gerät vertraut sein. TLS-Konfiguration: https://uvicorn.dev/settings/ .

## Zugriff vom iPhone

`SERVER_IP=0.0.0.0` setzen, neu starten und auf dem iPhone im selben WLAN
`http://<LAN-IP-des-Mac>:8080` öffnen (bei HTTPS entsprechend `https` und den eingestellten Port).
`0.0.0.0` ist keine Zieladresse im Browser. Firewall und WLAN müssen Verbindungen erlauben.
Bluetooth läuft ausschließlich auf dem Serverrechner: er muss eingeschaltet und nah am E10 sein.
Der Browser benötigt keine Web-Bluetooth-Unterstützung.

LAN-Modus nur in einem vertrauenswürdigen Netz, HTTPS empfohlen. Kein Portforwarding ins Internet.
Keine Authentifizierung: Jeder mit Netzwerkzugriff kann Drucker steuern und drucken.
HTTPS verschlüsselt die Verbindung, ersetzt aber keine Zugriffskontrolle.
Kein Benutzer-/Rechtesystem, keine Internet-Härtung. Nicht als öffentliches Druckgateway einsetzen.
`.env`, Schlüsseldateien und `printer.json` nicht veröffentlichen.

## Grenzen und Verifikation

- Offline-Tests: Betrieb ohne Anmeldung, Origin-Prüfung, Eingabelimits, Vorschau,
  simulierte Geräteauswahl, Befehlsrahmen, Datenrahmen, Pufferprüfsummen,
  fragmentierte Antworten und Kompression; kein echter Bluetooth-Scan in den Tests.
- Der Referenzdecoder liest den Python-LZMA-Strom korrekt zurück. Python/liblzma schreibt einen
  zusätzlichen Endmarker, während der Referenzencoder keinen schreibt. Damit ist das Format offline
  validiert, aber die Akzeptanz durch die E10-Firmware noch nicht nachgewiesen.
- BLE-Schreibkapazität muss mindestens 128 Bytes ohne Antwort erlauben. Bei kleinerem MTU bricht
  der Server ab, statt das Frameformat unkontrolliert in 20-Byte-Pakete umzuwandeln.
- Material wird vor Druck gelesen; unlesbare Daten oder unpassende gemeldete Stanzetikettenlänge
  verhindern den Start. Keine Umgehung der Materialerkennung oder Firmwareänderungen.
- Kein automatisches Neudrucken bei Verbindungsabbrüchen, keine parallelen Aufträge.
- Nur ein Prozess/Worker; nicht mit Reload oder mehreren Uvicorn-Workern betreiben.
- Verschieben zwischen Betriebssystemen erfordert neue Geräteauswahl: macOS nutzt Geräte-UUIDs,
  andere Systeme typischerweise Bluetooth-Adressen.

Tests:
```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest test_server -v
```
Node.js ist nur für den optionalen Test gegen den mitgelieferten Referenzdecoder nötig.

## Herkunft/Lizenz

Protokollport nach https://github.com/khromov/supvan-katasymbol-printer-web-ui
(`t15.ts`, `t5080-bt.ts`, `ble.ts`); Original-Lizenz und Referenzdateien in `reference/`.
Die Referenz beschreibt eine Rekonstruktion aus Supvan-Android- und iOS-Apps.
Das ist keine offizielle Supvan-API. Vorherige APK-Stringanalyse bestätigt Klassen/Methoden/UUIDs,
aber nicht die Ausführung dieses Python-Ports am Drucker.
