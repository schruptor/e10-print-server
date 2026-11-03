# Sicherheit

Dieser experimentelle Server ist für localhost oder ein vertrauenswürdiges LAN bestimmt,
nicht für eine direkte Veröffentlichung im Internet.

- Standardbindung auf 127.0.0.1 beibehalten, sofern kein LAN-Zugriff benötigt wird.
- Zufälligen ACCESS_TOKEN verwenden und bei Verdacht auf Offenlegung rotieren.
- Nach Änderungen an .env den Server neu starten.
- Im LAN HTTPS verwenden; HTTP überträgt den Schlüssel unverschlüsselt.
- Keine Portweiterleitung ins Internet einrichten.
- .env, private Schlüssel und printer.json niemals veröffentlichen.

Sicherheitsprobleme bitte vertraulich über GitHubs „Report a vulnerability“ melden,
falls für dieses Repository aktiviert. Andernfalls zunächst ein Issue ohne technische
Angriffsdetails oder Geheimnisse eröffnen, um einen privaten Kontaktweg zu vereinbaren.
