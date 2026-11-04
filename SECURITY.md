# Sicherheit

Dieser experimentelle Server ist für localhost oder ein vertrauenswürdiges LAN bestimmt,
nicht für eine direkte Veröffentlichung im Internet.

- Standardbindung auf 127.0.0.1 beibehalten, sofern kein LAN-Zugriff benötigt wird.
- Keine Authentifizierung: Jeder mit Netzwerkzugriff kann den Drucker steuern.
- Origin-Prüfung ist keine Zugriffskontrolle und schützt nicht vor direkten API-Aufrufen.
- Nach Änderungen an .env den Server neu starten.
- Im LAN HTTPS verwenden; dies verschlüsselt die Verbindung, beschränkt aber nicht den Zugriff.
- Keine Portweiterleitung ins Internet einrichten.
- .env, private Schlüssel und printer.json niemals veröffentlichen.

Sicherheitsprobleme bitte vertraulich über GitHubs „Report a vulnerability“ melden,
falls für dieses Repository aktiviert. Andernfalls zunächst ein Issue ohne technische
Angriffsdetails oder Geheimnisse eröffnen, um einen privaten Kontaktweg zu vereinbaren.
