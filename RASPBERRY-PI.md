# Raspberry Pi: E10-Verbindung mit BlueZ

## Verifizierter Stand

Auf einem Raspberry Pi 5 mit Debian 13 (ARM64), BlueZ 5.82 und Bleak 3.1.0
funktionieren Serverstart, Vorschau und die E10-Verbindung über die Web-API.
Die Verbindung wurde nach einem Neustart von Bluetooth und E10-Dienst erneut bestätigt.
Ein vollständiger Pi-Neustart und ein Hardwaredruck wurden in diesem Test nicht durchgeführt.

## Fehler: br-connection-profile-unavailable

Im untersuchten Fall sendete der E10 verbindbare BLE-Werbung (ADV_IND),
BlueZ versuchte aber anschließend eine klassische BR/EDR-Verbindung.
Dies wurde mit btmon beobachtet. Es handelt sich um einen konkreten Befund,
nicht um eine Erklärung für jeden Verbindungsfehler mit derselben Meldung.

Auf einem dedizierten Druckserver ohne klassische Bluetooth-Geräte half
**BLE-only-Betrieb**. Das ist eine Betriebssystem-Einstellung, keine Änderung
am Python-Druckprotokoll. Sie gilt für den gesamten Bluetooth-Controller:
klassische Bluetooth-Tastaturen, Audio-Geräte usw. können dadurch ausfallen.

## Dauerhafte Einstellung

Nur zwischen Druckaufträgen ausführen. Bluetooth-Verbindungen werden unterbrochen.

1. Konfiguration sichern:
   ```sh
   sudo cp -a /etc/bluetooth/main.conf /etc/bluetooth/main.conf.before-e10
   ```
   Einen bereits vorhandenen Backup-Namen nicht überschreiben.
2. `sudoedit /etc/bluetooth/main.conf` öffnen und unter `[General]` genau eine
   aktive Einstellung setzen (eine vorhandene Zeile ersetzen):
   ```ini
   ControllerMode = le
   ```
3. Dienste neu starten:
   ```sh
   sudo systemctl restart bluetooth
   sudo systemctl restart e10-print-server
   ```
4. Mit `btmgmt info` prüfen: `current settings` muss `le`, aber nicht `br/edr`
   enthalten. Danach den E10 auf der Webseite erneut verbinden.

Rückgängig machen: In derselben Datei `ControllerMode = dual` setzen und
beide Dienste erneut starten. Alternativ das zuvor erstellte Backup zurückspielen.

## Weiter prüfen

```sh
systemctl status bluetooth e10-print-server
journalctl -u e10-print-server -n 60 --no-pager
bluetoothctl show
```

Der Drucker muss eingeschaltet und in Reichweite sein. Parallele Verbindungen
vom Handy oder einem anderen Server trennen. Keine automatische Cache-Löschung,
Kopplung oder globale Controller-Umstellung im plattformübergreifenden Treiber:
die BLE-only-Einstellung wird bewusst vom Betreiber vorgenommen.
