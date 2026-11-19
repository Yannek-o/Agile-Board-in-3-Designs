# Agile Board

Eigenständige Django-Webanwendung zur Organisation mehrerer Softwareprojekte
nach Scrum: Product Backlog, Sprintplanung, interaktives Agile Board,
Teamverwaltung, Dashboard und Auswertungen.

Die Anwendung hat eine eigene Datenbank, eigene Anmeldung und eigene
Konfiguration; das Design setzt auf ein dunkles Theme mit orangefarbenen
Akzenten (weitere Designs: „Patina“ und „Kalt“).

> Gedacht für den Einsatz in einem Team oder Unternehmen. Es gibt keine
> öffentliche Registrierung – Konten werden von der Systemadministration angelegt.

## Inhalt

- [Funktionsumfang](#funktionsumfang)
- [Technologien](#technologien)
- [Projektstruktur](#projektstruktur)
- [Django-Apps](#django-apps)
- [Installation](#installation)
- [Umgebungsvariablen](#umgebungsvariablen)
- [PostgreSQL](#postgresql)
- [Anwendung starten](#anwendung-starten)
- [Tests und Codequalität](#tests-und-codequalität)
- [Berechtigungen](#berechtigungen)
- [Zusammenarbeit über Git](#zusammenarbeit-über-git)
- [Entwicklungsstand](#entwicklungsstand)

## Funktionsumfang

| Bereich | Umgesetzt |
| --- | --- |
| Anmeldung | Login/Logout (nur POST), Profil, Passwort ändern, globale Login-Pflicht, Login-Sperre nach Fehlversuchen (je Konto und je IP, auch im Admin), Passwort-Reset per E-Mail |
| Benachrichtigungen | Glocke in der Navigationsleiste (In-App) bei Zuweisung, @Erwähnung, Kommentar und Statusänderung beobachteter Einträge; Beobachter je Eintrag (Ersteller, Bearbeiter und Kommentierende automatisch); E-Mails bei Zuweisung, Erwähnung, Kommentar und Sprintstart/-abschluss, Versand erst nach erfolgreichem Commit, im Profil abschaltbar |
| Mitarbeiterkonten | Anlegen per Einladung (E-Mail mit Link, 7 Tage gültig, Mitarbeiter setzt sein Passwort selbst; erneut senden möglich), Bearbeiten, Aktivieren/Deaktivieren, Recht „Projekte anlegen“, Protokoll aller Kontoänderungen, mindestens eine aktive Systemadministration bleibt immer erhalten |
| Projekte | Anlegen, Bearbeiten, Archivieren/Wiederherstellen, Suche, Statusfilter, Product Goal, Definition of Done, WIP-Limits für „In Progress“ und „In Review“; Workflow je Projekt: eigene Spaltennamen, Review-Spalte abschaltbar, Regeln (Review-Pflicht vor Done, Done nur durch Projektleitung/Product Owner, Done nur mit erfüllten Akzeptanzkriterien) – zentral geprüft, Begründung erscheint auf dem Board |
| Team | Mitglieder zuweisen, Scrum-Verantwortlichkeit und technische Rechte getrennt, Schutz der letzten Projektleitung |
| Product Backlog | Epic, User Story, Aufgabe, Bug, technische Verbesserung, Unteraufgabe; Hierarchie Epic → Story → Unteraufgabe mit Fortschritt; Epic-Übersicht mit Kennfarbe und Story-Point-Fortschritt, Filter nach Epic; Verknüpfungen (blockiert, gehört zu, Duplikat); IDs (`HELP-12`), Akzeptanzkriterien, Priorität, Story Points, Bearbeiter, Labels, Fälligkeit, Blockiert-Kennzeichen; Planungsansicht wie in Jira (Sprints oben, Backlog darunter, Einplanen per Drag & Drop); Inline-Bearbeitung in Detailansicht und Dialog; Suchen, Filtern, Sortieren, Archivieren (archivierte Einträge verlassen offene Sprints); Reihenfolge per Drag & Drop oder ▲/▼; Releases (Fix-Version) mit Fortschritt, Veröffentlichen und Filter; Zeiterfassung mit Schätzung, Zeitbuchungen („1h 30m“, „1d“) und automatisch sinkendem Restaufwand |
| Kommentare, Anhänge & Links | Kommentare mit @Erwähnungen (Vorschläge beim Tippen), geschützte Datei-Uploads mit Typ- und Größenprüfung sowie Virenprüfung über ClamAV, Download nur mit Projektrecht; Anhänge und Links schon beim Anlegen (Drag & Drop, Screenshot per Strg+V), Bildvorschau; Web-Links (nur http/https) je Eintrag |
| Sprints | Anlegen, Sprint-Ziel, Zeitraum (max. 1 Monat), Einträge zuordnen, Starten, Abschließen (Übernahme in Folgesprint oder zurück ins Backlog), Abbrechen, Historie, Fortschrittsbalken nach Status mit Resttagen, Kapazitätshinweis in der Sprintplanung (geplante Story Points gegenüber Ø der letzten 3 Sprints, Warnung ab 15 % darüber), Retrospektive (Was lief gut / nicht gut / Was ändern wir) mit Anzeige der Maßnahmen im nächsten Sprint, Sprint-Bericht (erledigt, nicht erledigt, nach dem Start hinzugefügt, entfernt, Umfangsänderung) |
| Agile Board | Spalten To Do / In Progress / In Review / Done, Drag & Drop mit sofortiger Speicherung, Tastatur-/No-JS-Alternative, Detail-Dialog, Swimlanes (Bearbeiter, Epic, Priorität), Schnellfilter (Nur meine, Zuletzt geändert, Überfällig), neue Karten direkt in der Spalte anlegen, Epic-Chip, Unteraufgaben-Fortschritt und offene Blocker auf der Karte, Priorität als farbiger Text oben rechts (hohe/kritische Karten in „To Do“ mit rotem Rand), Detail-Dialog bleibt beim Speichern offen (Formulare werden im Hintergrund gesendet, Board aktualisiert sich), Filter (Bearbeiter, Priorität, Typ, blockiert), Ansicht vergangener Sprints, Konflikterkennung bei gleichzeitigen Änderungen, Live-Aktualisierung (Änderungen anderer erscheinen automatisch), rot leuchtende Hervorhebung überfälliger Karten und Sprints (Projektliste: „In Verzug“), WIP-Limit-Warnung (Spalte rot, zählt über alle Swimlanes) |
| Dashboard | Aktive Projekte, laufende Sprints, eigene offene Aufgaben, erledigt im Sprint, hohe Priorität, blockiert – jede Kachel klappt die betroffenen Einträge auf und zeigt Icon, Trend gegenüber der Vorwoche (bzw. dem ältesten bekannten Stand) und Verlaufskurve der letzten 14 Tage aus täglichen Ständen je Benutzer (`DashboardSnapshot`, 60 Tage aufbewahrt); Signalfarben bei Blockiertem, hoher Priorität und vollständig erledigtem Sprint; Sprint-Fortschritt, zuletzt geändert – alles live aus der Datenbank; persönliche Notizen (automatisch gespeichert, nur für den eigenen Benutzer sichtbar) |
| Rückmeldungen | Meldungen als Toasts unten rechts (blenden automatisch aus, pausieren bei Maus/Fokus); „Rückgängig“ beim Archivieren eines Eintrags und beim Verschieben einer Karte auf dem Board; Skeleton-Ladezustände im Detail-Dialog und in der Schnellsuche |
| Berichte | Burndown-Diagramm (Sprintseite und Projektbericht) mit Raster, Linie „Heute“ und Abweichung zum Plan, Burnup (Umfang und Erledigt), Velocity-Diagramm (geplant/erledigt je Sprint mit Durchschnitt), Cumulative Flow (Einträge je Status pro Tag), Status- und Typverteilung, offene Arbeit je Person, abgeschlossene Sprints – alle Diagramme serverseitig als SVG aus der Statushistorie |
| Änderungsprotokoll | Jede fachliche Änderung als `ActivityEvent` (wer, wann, Feld, alt → neu) |
| Markdown | Beschreibungen und Kommentare mit Überschriften, Listen, Aufgabenlisten, Zitaten, Code und Links – sicher gerendert (erst escapen, dann formatieren) |
| Suche & Filter | Globale Suche über alle eigenen Projekte (ID wie `HELP-12`, Titel, Beschreibung); gespeicherte Backlog-Filter als Chips, privat oder fürs Team geteilt |
| Massenbearbeitung | Mehrere Einträge in der Backlog-Liste auswählen und Status, Bearbeiter, Priorität, Sprint oder Release setzen bzw. archivieren – jede Änderung läuft durch dieselben Regeln (Workflow, Rechte, Protokoll); abgelehnte Einträge werden einzeln gemeldet |
| CSV | Export der (gefilterten) Backlog-Liste für Excel (UTF-8, Semikolon, Schutz vor Formel-Injection); Import mit Spaltenerkennung (deutsch/englisch, `;` oder `,`), vollständiger Prüfung vorab und Fehlerbericht je Zeile – importiert wird alles oder nichts |
| Schnellzugriff | Befehlspalette mit <kbd>Strg</kbd>+<kbd>K</kbd> (Einträge und Befehle), Tastenkürzel (`g b` Board, `g l` Backlog, `c` neuer Eintrag, `/` Suche, `?` Hilfe) |
| Planning Poker | Schätzrunde je Eintrag: verdeckt abstimmen (Fibonacci-Karten, `?`, ☕), Aufdecken mit Ø/Min/Max und Vorschlag, neue Runde, Story Points übernehmen – Stand aktualisiert sich bei allen automatisch |
| REST-API | JSON-API unter `/api/v1/` für Projekte, Einträge (Liste mit Backlog-Filtern, Detail, Anlegen, Ändern inkl. Versionsprüfung) und Sprints; persönliche API-Tokens (nur als Hash gespeichert, jederzeit widerrufbar) oder Sitzung mit CSRF-Schutz; gleiche Rechte wie in der Oberfläche |

## Technologien

- Python 3.12, Django 5.2 LTS
- PostgreSQL (getestet mit 16) über `psycopg` 3
- Django Templates, HTML5, CSS3 (zentrale CSS-Variablen), Vanilla JavaScript
- Bootstrap 5.3 (lokal unter `static/vendor/`, kein CDN)
- Eigenes Designsystem „Dark Neon“ in `static/css/app.css` mit Hell/Dunkel-Umschalter
  (`static/js/theme.js`) und Animationen (`static/js/effects.js`); bei der
  Systemeinstellung „Bewegung reduzieren“ sind alle Animationen abgeschaltet
- Zweites Design „Patina“ (Petrol/Kupfer, Glas- und Metallflächen) als Zusatzschicht
  `static/css/patina.css` mit stufenlosem Helligkeitsregler (`static/js/patina-theme.js`)
  und Drag-Spur auf dem Board (`static/js/board-effects.js`). Jeder Mitarbeiter wählt
  sein Design im Benutzermenü oder unter „Mein Profil“; gespeichert im Konto
  (`User.design`, Standard „Neon“). Funktionen sind in beiden Designs identisch
- Persönliche Avatar-Farbe: Im Benutzermenü neben „Mein Profil“ wählt jeder eine
  Farbe oder einen Verlauf aus zwei Farben (mit Vorschlägen, Live-Vorschau und
  automatischem Speichern). Sie gilt in allen Designs und überall, wo das Kürzel
  erscheint; die Schriftfarbe wird für gute Lesbarkeit automatisch gewählt
- Optionales eigenes Logo unter `static/img/brand/` (sonst Schriftzug „Agile Board“)

## Projektstruktur

```
├── apps/
│   ├── core/          # Navigation, Template-Tags, HTTP-Helfer, Demo-Daten-Befehl
│   ├── accounts/      # Benutzer-Modell, Login, Profil, Mitarbeiterverwaltung
│   ├── projects/      # Projekte, Mitgliedschaften, Labels, Berechtigungslogik
│   ├── backlog/       # Backlog-Einträge, Kriterien, Kommentare, Anhänge
│   ├── sprints/       # Sprints, Sprint-Einträge (Historie), Sprint-Lebenszyklus
│   ├── board/         # Agile Board und Status-Endpunkt
│   ├── reporting/     # Dashboard, Projektberichte, Burndown
│   ├── notifications/ # E-Mail-Benachrichtigungen
│   ├── activity/      # Änderungsprotokoll
│   ├── poker/         # Planning Poker
│   └── api/           # REST-API v1 und API-Tokens
├── config/
│   ├── settings/      # base, development, production, test
│   ├── env.py         # Laden von Umgebungsvariablen / .env
│   └── urls.py
├── docs/architecture.md
├── scripts/run_with_pg.py   # optionales eingebettetes PostgreSQL für Entwicklung
├── static/            # css/app.css, js/*.js, vendor/bootstrap
├── templates/         # Basislayout, Includes und App-Templates
├── tests/             # automatisierte Tests
├── manage.py
├── requirements.txt
└── requirements-dev.txt
```

## Django-Apps

Jede App kapselt ihre Modelle, Services (Geschäftsregeln), Formulare, Views und
URLs. Schreibende Operationen laufen über die `services.py` der jeweiligen App.
Dadurch können mehrere Entwickler unabhängig an einzelnen Apps arbeiten.

| App | Verantwortung | Wichtige Dateien |
| --- | --- | --- |
| `accounts` | Eigenes `User`-Modell (`AUTH_USER_MODEL = "accounts.User"`), Login mit Sperre nach Fehlversuchen, Passwort-Reset, Profil, Kontenverwaltung | `models.py`, `views.py`, `throttling.py` |
| `projects` | `Project`, `ProjectMembership`, `Label`; zentrale Rechteprüfung | `permissions.py`, `mixins.py` |
| `backlog` | `BacklogItem` (mit Epic/Unteraufgabe-Hierarchie), `ItemLink`, `AcceptanceCriterion`, `Comment`, `Attachment`, `SavedFilter`; Anlage, Änderungen mit optimistischem Locking, Priorisierung, Planungsansicht, Inline-Bearbeitung, Massenbearbeitung, CSV-Import/-Export, Virenprüfung | `services.py`, `queries.py`, `bulk.py`, `csv_io.py`, `scanning.py` |
| `sprints` | `Sprint`, `SprintItem`; Planen, Starten, Abschließen, Abbrechen | `services.py` |
| `board` | Board-Ansicht mit Swimlanes und Schnellfiltern, `move`-, `create`- und `state`-Endpunkt (Live-Aktualisierung) | `views.py`, `lanes.py`, `static/js/board.js` |
| `reporting` | Kennzahlen für Dashboard und Berichte, Burndown | `services.py`, `burndown.py` |
| `notifications` | In-App-Benachrichtigungen (`Notification`), Beobachter (`ItemWatch`), @Erwähnungen, E-Mails (Versand nach Commit) | `models.py`, `services.py`, `context_processors.py` |
| `activity` | `ActivityEvent` und Protokollansicht | `services.py` |
| `poker` | `PokerSession`, `PokerVote`; Abstimmen, Aufdecken, Übernehmen der Schätzung | `services.py`, `static/js/poker.js` |
| `api` | `ApiToken`; Authentifizierung (Bearer-Token oder Sitzung + CSRF), JSON-Endpunkte v1 | `auth.py`, `views.py` |
| `core` | Kontext-Prozessor, Template-Tags, Markdown, globale Suche, `seed_demo` | `templatetags/agile.py`, `markdown.py`, `search.py` |

Architekturentscheidungen sind in [docs/architecture.md](docs/architecture.md)
dokumentiert.

## Installation

Voraussetzungen: Python 3.12+, Git und eine PostgreSQL-Datenbank (alternativ das
eingebettete Entwicklungs-PostgreSQL, siehe unten).

```powershell
git clone https://github.com/Yannek-o/Agile-Board-in-3-Designs.git
cd Agile-Board-in-3-Designs

python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt   # Produktion: requirements.txt

Copy-Item .env.example .env           # Linux/macOS: cp .env.example .env
```

Danach in `.env` mindestens `DJANGO_SECRET_KEY` setzen:

```powershell
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

## Umgebungsvariablen

Alle Werte werden aus der Umgebung oder aus `.env` gelesen (`.env` ist in
`.gitignore`). Es werden keine Zugangsdaten im Repository gespeichert.

| Variable | Pflicht | Standard | Beschreibung |
| --- | --- | --- | --- |
| `DJANGO_SECRET_KEY` | ja | – | Geheimer Schlüssel (Produktion: ≥ 50 Zeichen) |
| `DJANGO_DEBUG` | nein | `true` (nur development) | Debug-Modus |
| `DJANGO_ALLOWED_HOSTS` | Produktion | `localhost,127.0.0.1` (development) | Kommagetrennte Hostnamen |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | nein | – | z. B. `https://agile.example.com` |
| `DJANGO_MEDIA_ROOT` | nein | `./media` | Ablage für Anhänge (nicht öffentlich ausgeliefert) |
| `DJANGO_SECURE_SSL_REDIRECT` | nein | `true` (production) | HTTPS-Weiterleitung |
| `DJANGO_SECURE_HSTS_SECONDS` | nein | `31536000` (production) | HSTS-Dauer |
| `POSTGRES_DB` | nein | `agile_board` | Datenbankname |
| `POSTGRES_USER` | nein | `agile_board` | Datenbankbenutzer |
| `POSTGRES_PASSWORD` | ja (real) | leer | Passwort |
| `POSTGRES_HOST` | nein | `localhost` | Host |
| `POSTGRES_PORT` | nein | `5432` | Port |
| `POSTGRES_CONN_MAX_AGE` | nein | `60` | Persistente Verbindungen (Sekunden) |
| `ATTACHMENT_MAX_UPLOAD_BYTES` | nein | `10485760` | Maximale Anhangsgröße |
| `SITE_URL` | Produktion | `http://localhost:8000` | Öffentliche Basis-URL für Links in E-Mails (Produktion: `https://` Pflicht) |
| `EMAIL_BACKEND` | nein | SMTP (development: Konsole) | Django-E-Mail-Backend |
| `EMAIL_HOST` / `EMAIL_PORT` | für E-Mail | `localhost` / `587` | SMTP-Server |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | nein | leer | SMTP-Zugangsdaten |
| `EMAIL_USE_TLS` / `EMAIL_USE_SSL` | nein | `true` / `false` | Transportverschlüsselung |
| `EMAIL_TIMEOUT` | nein | `10` | SMTP-Timeout (Sekunden) |
| `DEFAULT_FROM_EMAIL` | nein | `Agile Board <agile-board@localhost>` | Absender |
| `PASSWORD_RESET_TIMEOUT` | nein | `7200` | Gültigkeit von Reset-Links (Sekunden) |
| `INVITATION_TIMEOUT` | nein | `604800` | Gültigkeit von Einladungslinks für neue Konten (Sekunden) |
| `LOGIN_FAILURE_LIMIT` | nein | `5` | Fehlversuche je Benutzername bis zur Sperre |
| `LOGIN_IP_FAILURE_LIMIT` | nein | `20` | Fehlversuche je IP-Adresse bis zur Sperre |
| `LOGIN_LOCKOUT_MINUTES` | nein | `15` | Sperrdauer bzw. Beobachtungszeitraum |
| `PASSWORD_RESET_IP_LIMIT` | nein | `5` | Reset-Anfragen je IP und Stunde |
| `TRUST_X_FORWARDED_FOR` | nein | `false` | Client-IP aus `X-Forwarded-For` lesen (nur hinter vertrauenswürdigem Proxy) |
| `ATTACHMENT_VIRUS_SCAN` | nein | `disabled` (production: `clamav`) | Virenprüfung: `disabled` oder `clamav` |
| `ATTACHMENT_SCAN_FAIL_CLOSED` | nein | `true` | Uploads ablehnen, wenn ClamAV nicht erreichbar ist |
| `CLAMAV_HOST` / `CLAMAV_PORT` | bei `clamav` | `127.0.0.1` / `3310` | clamd-Adresse (TCP) |
| `CLAMAV_TIMEOUT` | nein | `30` | Timeout der Prüfung (Sekunden) |
| `BOARD_POLL_INTERVAL_SECONDS` | nein | `10` | Abfrageintervall der Live-Aktualisierung |

Settings-Module: `config.settings.development` (Standard für `manage.py`),
`config.settings.production` (Standard für WSGI/ASGI), `config.settings.test`.

## PostgreSQL

### Variante A – vorhandener PostgreSQL-Server (empfohlen, Pflicht für Produktion)

```sql
CREATE ROLE agile_board LOGIN PASSWORD '<sicheres-passwort>';
CREATE DATABASE agile_board OWNER agile_board ENCODING 'UTF8';
-- Für "manage.py test" benötigt der Benutzer das Recht, Testdatenbanken anzulegen:
ALTER ROLE agile_board CREATEDB;
```

Zugangsdaten in `.env` eintragen und migrieren:

```powershell
python manage.py migrate
python manage.py createsuperuser
```

### Variante B – eingebettetes PostgreSQL nur für die Entwicklung

Ohne lokale PostgreSQL-Installation kann das optionale Paket `pgserver`
(in `requirements-dev.txt`) einen PostgreSQL-16-Server im Ordner `.pgdata/`
starten. `scripts/run_with_pg.py` startet den Server bei Bedarf, legt die
Datenbank an, setzt die `POSTGRES_*`-Variablen und führt den übergebenen
`manage.py`-Befehl aus:

```powershell
python scripts/run_with_pg.py migrate
python scripts/run_with_pg.py createsuperuser
python scripts/run_with_pg.py runserver
python scripts/run_with_pg.py test --settings=config.settings.test
```

Unter Windows fehlen dem `pgserver`-Paket die Zeitzonendaten; das Skript
kopiert sie beim ersten Start einmalig aus dem Python-Paket `tzdata`.
Der Server läuft nach dem Befehl im Hintergrund weiter (Daten bleiben in
`.pgdata/`).

## Anwendung starten

```powershell
python manage.py migrate
python manage.py createsuperuser        # erstes Administrationskonto
python manage.py runserver
```

Aufruf: <http://127.0.0.1:8000/> – Anmeldung mit dem angelegten Konto.

Optionale Demo-Daten (nur mit `DJANGO_DEBUG=true`): Projekte HELP, SHOP und
DATA, vier fiktive Konten (`anna`, `ben`, `clara`, `david`) mit einem frei
gewählten Passwort und ein aktiver Sprint:

```powershell
python manage.py seed_demo              # Passwort wird abgefragt
```

### Manuelle Prüfung

1. Als `ben` anmelden → Dashboard zeigt Kennzahlen aus der Datenbank.
2. **Agile Board** → Karte per Drag & Drop verschieben → Seite neu laden →
   Karte steht in der neuen Spalte.
3. Ohne Maus: Status im Kartenfeld wählen und „Verschieben“ drücken.
4. Karte anklicken → Detaildialog mit Kriterien, Kommentaren, Verlauf.
5. Als `david` (nur Lesen) anmelden → Board ist sichtbar, aber nicht änderbar.
6. Fremde Projekt-URL als Nutzer ohne Mitgliedschaft aufrufen → 404.

### Produktion (Kurzüberblick)

- `DJANGO_SETTINGS_MODULE=config.settings.production`, `DJANGO_DEBUG` nicht setzen.
- `python manage.py collectstatic` und `python manage.py check --deploy`.
- Betrieb hinter einem Reverse Proxy mit HTTPS (z. B. gunicorn/uWSGI + nginx);
  statische Dateien aus `STATIC_ROOT` über den Webserver ausliefern.
- `DJANGO_MEDIA_ROOT` auf ein gesichertes Verzeichnis setzen; Anhänge werden
  ausschließlich über die berechtigungsgeprüfte Download-View ausgeliefert –
  das Verzeichnis darf **nicht** öffentlich freigegeben werden.
- Regelmäßige Backups von PostgreSQL und `DJANGO_MEDIA_ROOT`.

## Tests und Codequalität

Die Tests laufen gegen PostgreSQL (Constraints wie „max. ein aktiver Sprint“
und Zeilensperren werden real geprüft):

```powershell
python manage.py test --settings=config.settings.test
# ohne lokale PostgreSQL-Installation:
python scripts/run_with_pg.py test --settings=config.settings.test

pycodestyle --max-line-length=88 --exclude=migrations,.venv apps config tests scripts manage.py
python manage.py makemigrations --check --dry-run
```

| Testdatei | Inhalt |
| --- | --- |
| `tests/test_accounts.py` | Login/Logout, inaktive Konten, Profil ohne Rechteausweitung, Kontenverwaltung, Einladung per E-Mail, Kontoprotokoll, Schutz der letzten Systemadministration |
| `tests/test_permissions.py` | Rechtematrix, Trennung Scrum-Rolle/Rechte, sichtbare Projekte |
| `tests/test_projects.py` | Modelle, Formularvalidierung, Projekt-CRUD, Archivierung, Team, Labels, 404 für fremde Projekte |
| `tests/test_backlog.py` | Nummernvergabe, Priorisierung, optimistisches Locking, Statushistorie, Uploads, Suche/Filter, XSS-Escaping, eingeschränkte Bearbeitung, projektübergreifende Zugriffe |
| `tests/test_sprints.py` | Sprintlänge, Planung, ein aktiver Sprint (Service + DB-Constraint), Abschluss mit Übernahme/Historie, Abbruch, Retrospektive, Kapazität gegenüber Velocity |
| `tests/test_board.py` | Spalten, Filter, Drag-&-Drop-Endpunkt (JSON), Formular-Fallback, Konflikt (409), CSRF, Leserechte, ungültige Status, Revisions-Endpunkt für Live-Aktualisierung, WIP-Limit |
| `tests/test_reporting.py` | Dashboard-Kennzahlen mit aufklappbaren Listen, persönliche Notizen, Sprint-Fortschritt nach Status, Berichte, Burndown aus Statushistorie (Raster, Heute, Plan-Abweichung), Änderungsprotokoll, Navigation (zuletzt genutztes Projekt, sonst Projekt mit laufendem Sprint) |
| `tests/test_security.py` | Login-Sperre je Konto/IP (inkl. Admin-Login), Passwort-Reset (vollständiger Ablauf, keine Konto-Enumeration, Drosselung je IP) |
| `tests/test_notifications.py` | Benachrichtigungen bei Zuweisung, Kommentar, Sprintstart/-abschluss; Opt-out; fehlerhafter Mailserver bricht keine Aktion ab |
| `tests/test_scanning.py` | ClamAV-Protokoll gegen Test-Server (sauber, EICAR, nicht erreichbar), Fail-closed/Fail-open beim Upload |
| `tests/test_branding.py` | Logo aus `static/img/brand/` bzw. Schriftzug als Ersatz, Theme-Umschalter und Effekte auf App- und Anmeldeseiten |
| `tests/test_design.py` | Design-Wahl je Benutzer (Neon/Patina), passende Stylesheets und Hell/Dunkel-Steuerung, Umschalten nur per POST mit sicherer Weiterleitung, Profilformular |
| `tests/test_avatar_color.py` | Avatar-Farbe und Verlauf speichern, Zurücksetzen, nur gültige Farbwerte, lesbare Schriftfarbe, Anzeige in allen Designs und für Kollegen |
| `tests/test_sprint_report.py` | Sprint-Bericht: Gruppen erledigt/nicht erledigt/hinzugefügt/entfernt, Umfangszahlen, offener und abgeschlossener Sprint |
| `tests/test_charts.py` | Velocity, Burnup und Cumulative Flow aus Sprint-Einträgen und Statushistorie, junge Projekte, archivierte Einträge |
| `tests/test_time_tracking.py` | Dauer-Eingabe („1h 30m“, „1d“), Buchen und Löschen, Restaufwand, Rechte, Schätzung im Formular |
| `tests/test_releases.py` | Release-Fortschritt, gleiches Projekt, eindeutige Namen, Veröffentlichen, Filter, nur offene Releases im Formular |
| `tests/test_workflow.py` | Workflow-Regeln (Review-Pflicht, Done nur durch Leitung/PO, Akzeptanzkriterien), eigene Spaltennamen, ausgeblendete Review-Spalte, Projektformular |
| `tests/test_overdue.py` | Überfällige Einträge (Fälligkeit überschritten, nicht Done), überfällige Sprints, Hervorhebung auf Board und Projektliste |
| `tests/test_hierarchy.py` | Epic/Story/Unteraufgabe-Regeln, Fortschritt, Protokoll, Epics nicht im Sprint, Anzeige auf Detailseite und Board |
| `tests/test_links.py` | Verknüpfungen beidseitig, keine Selbst-/Doppel-/Projektübergreifenden Links, Rechte, „Blockiert durch“ auf dem Board |
| `tests/test_planning.py` | Verschieben zwischen Sprints und Backlog (atomar), Planungsansicht, JSON/Formular, Rechte |
| `tests/test_quick_edit.py` | Schnell anlegen im aktiven Sprint, Inline-Bearbeitung mit Typumwandlung, Rechten und Versionskonflikt |
| `tests/test_swimlanes.py` | Swimlanes nach Bearbeiter/Epic/Priorität, Schnellfilter einzeln und kombiniert, WIP-Limit über alle Swimlanes |
| `tests/test_mentions.py` | @Erwähnungen, Beobachter, In-App-Benachrichtigungen, Glocke, Lesestatus, HTML-Escaping |
| `tests/test_web_links.py` | Anlegen mit Anhängen und Links, Ablehnung unzulässiger Dateien/URLs ohne Teilanlage, Web-Links mit Rechten, Bildvorschau |
| `tests/test_epic_overview.py` | Epic-Fortschritt (nur aktive Einträge), Epic-Seite mit Farbe, Rechte, Backlog-Filter nach Epic inkl. Unteraufgaben |
| `tests/test_markdown.py` | Markdown-Elemente, Escaping vor Formatierung, nur http(s)-Links, Erwähnungen außerhalb von Code |
| `tests/test_search.py` | Globale Suche (Text, ID, nur sichtbare und aktive Einträge, JSON), gespeicherte Filter (bereinigte Parameter, privat/geteilt, nur Besitzer löscht), Befehlspalette |
| `tests/test_bulk_edit.py` | Massenänderung von Status, Bearbeiter, Priorität, Sprint, Archiv; Workflow-Verstöße einzeln gemeldet; fremde Einträge ignoriert; Rechte |
| `tests/test_csv.py` | Export mit Filtern und Formel-Schutz, Import mit Bezeichnungen oder Codes, Komma/Semikolon, alles-oder-nichts mit Zeilenbericht, Rechte, Export→Import |
| `tests/test_poker.py` | Verdeckte Stimmen, eigene Karte sichtbar, Aufdecken mit Vorschlag, neue Runde, Übernahme der Story Points, Rechte |
| `tests/test_api.py` | Token nur als Hash, 401/404/403, widerrufene Tokens, Sitzung mit CSRF, Filter, Anlegen/Ändern, Versionskonflikt (409), Workflow-Regeln |

## Berechtigungen

Scrum-Verantwortlichkeiten (Product Owner, Scrum Master, Developer,
Stakeholder) sind rein fachlich. Systemaktionen werden ausschließlich über die
**technischen Rechte** der Projektmitgliedschaft gesteuert:

| Aktion | System-Admin | Projektleitung | Bearbeitung | Nur Lesen |
| --- | --- | --- | --- | --- |
| Benutzer verwalten | ja | nein | nein | nein |
| Projekt & Team verwalten | ja | eigenes Projekt | nein | nein |
| Backlog & Sprint pflegen | ja | ja | nach Freigabe | nein |
| Kartenstatus ändern, kommentieren, Bearbeiter/Beschreibung pflegen | ja | ja | ja | nein |
| Projektdaten ansehen | alle | eigenes Projekt | zugewiesen | zugewiesen |

- System-Admin = aktives Konto mit `is_staff` oder `is_superuser`.
- Neue Projekte dürfen System-Admins und Konten mit „Darf Projekte anlegen“
  erstellen; der Ersteller wird Projektleitung.
- Jede View prüft Rechte serverseitig (`ProjectAccessMixin`). Nicht-Mitglieder
  erhalten **404**, um die Existenz fremder Projekte nicht preiszugeben;
  Mitglieder ohne ausreichende Rechte erhalten **403**. Die REST-API wendet
  dieselben Regeln an (zusätzlich **401** ohne gültige Anmeldung).

## Zusammenarbeit über Git

- `main` – stabiler Hauptbranch, keine direkten Commits, Merge nur per Pull Request.
- `feature/<thema>` bzw. `development-<name>` – Entwicklungsbranches.

Empfehlungen:

1. Vor Arbeitsbeginn `git fetch` und `main` in den eigenen Branch übernehmen.
2. Arbeit möglichst entlang der App-Grenzen aufteilen (z. B. eine Person
   `reporting`, eine Person `board`), um Konflikte zu vermeiden.
3. Gemeinsame Dateien mit hohem Konfliktpotenzial: `config/settings/base.py`,
   `config/urls.py`, `templates/base.html`, `static/css/app.css`, Migrationen.
   Änderungen daran kurz abstimmen.
4. Migrationen nie nachträglich ändern, wenn sie bereits in einem anderen
   Branch liegen – stattdessen neue Migration anlegen. Bei parallelen
   Migrationen derselben App: `python manage.py makemigrations --merge`.
5. Vor jedem Push alle Tests ausführen.

## Entwicklungsstand

Umgesetzt sind Backlog, Sprints, Board, Team, Dashboard und Berichte (siehe
Funktionsumfang), ergänzt um Burndown, Live-Board, Login-Sperre, Passwort-Reset und
Benachrichtigungen per E-Mail sowie Virenprüfung von Uploads. Dazu kommen die
Jira-nahen Erweiterungen: Sprint-Bericht, Velocity/Burnup/Cumulative Flow,
Zeiterfassung, Releases, Workflow-Regeln, Markdown, globale Suche mit
gespeicherten Filtern, Massenbearbeitung, CSV-Import/-Export, Befehlspalette
mit Tastenkürzeln, Planning Poker und REST-API.
Bewusst **noch nicht** umgesetzt bzw. offen:

- Die Live-Aktualisierung nutzt Polling (Standard alle 10 s), keine
  WebSockets – dafür ohne zusätzliche Infrastruktur unter WSGI lauffähig.
- Für E-Mails und Virenprüfung werden ein SMTP-Server und ein ClamAV-Dienst
  (`clamd`) benötigt; beide müssen selbst bereitgestellt werden.
- Keine SSO-Anbindung (z. B. OpenID Connect).
