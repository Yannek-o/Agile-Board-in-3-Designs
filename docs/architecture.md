# Architekturentscheidungen

Stand: 17.11.2026. Die Entscheidungen sind kurz begründet, damit sie bei
späteren Änderungen gezielt geprüft werden können.

## ADR-01 Eigenständiges Django-Projekt mit App-Grenzen nach Fachbereich

Apps: `accounts`, `projects`, `backlog`, `sprints`, `board`, `reporting`,
`activity` (+ `core` für Querschnittsfunktionen). Abhängigkeiten zeigen nur in
eine Richtung: `accounts ← projects ← backlog ← sprints ← board/reporting`.
`activity` wird von allen Apps über `activity.services.record_event` genutzt.
Jede App besitzt eigene `urls.py`; projektbezogene Apps werden in
`config/urls.py` unter `projects/<key>/…` eingebunden.

## ADR-02 Eigenes User-Modell vor der ersten Migration

`accounts.User` erweitert `AbstractUser` um `job_title` und
`can_create_projects`; E-Mail-Adressen sind case-insensitiv eindeutig
(DB-Constraint). Spätere Erweiterungen (z. B. SSO-ID) sind ohne
Migrationsbruch möglich.

## ADR-03 Scrum-Verantwortlichkeit ≠ technische Berechtigung

`ProjectMembership` speichert `scrum_role` (Product Owner, Scrum Master,
Developer, Stakeholder) und `access_level` (Projektleitung, Bearbeitung, Nur
Lesen) getrennt, zusätzlich `can_manage_backlog` für „Bearbeiten nach
Freigabe“. Die gesamte Rechteauswertung liegt in `projects/permissions.py`
(`ProjectAccess`). Views nutzen ausschließlich `ProjectAccessMixin` mit
`required_permission`.

- Nicht-Mitglieder → 404 (keine Preisgabe fremder Projektkürzel),
  fehlende Rechte → 403.
- Entscheidung zur offenen Frage „Sehen alle Mitarbeiter alle Projekte?“:
  **Nein**, nur Mitglieder und System-Admins (sicherer Standard, leicht
  änderbar in `visible_projects`).
- Mitgliedschaften werden beim Entfernen deaktiviert, nicht gelöscht
  (Historie bleibt erhalten). Die letzte aktive Projektleitung kann nicht
  entfernt oder herabgestuft werden.

## ADR-04 Geschäftslogik in Service-Funktionen

Schreibende Operationen (`create_backlog_item`, `update_backlog_item`,
`change_item_status`, `add_item_to_sprint`, `complete_sprint`, …) liegen in
`services.py` der jeweiligen App. Sie validieren, sperren betroffene Zeilen
(`SELECT … FOR UPDATE`) und schreiben das Änderungsprotokoll. Views bleiben
dünn; Board, Backlog-Detail und Formulare nutzen dieselben Funktionen.

## ADR-05 Fortlaufende Aufgaben-IDs je Projekt

`BacklogItem.number` wird aus `Project.next_item_number` unter Zeilensperre
vergeben; Anzeige als `<KÜRZEL>-<Nummer>` (z. B. `HELP-24`). Eindeutigkeit
zusätzlich per DB-Constraint `(project, number)`. Projektkürzel sind nach dem
Anlegen unveränderlich, damit IDs stabil bleiben. Sprints werden analog
nummeriert.

## ADR-06 Backlog-Reihenfolge unabhängig von der Priorität

`backlog_rank` speichert die Product-Backlog-Reihenfolge; `priority` ist eine
separate Kennzeichnung. Umsortieren (Drag & Drop oder ▲/▼) nummeriert die
aktiven Einträge eines Projekts in einer Transaktion neu. Für typische
Backloggrößen (< einige tausend Einträge) ist das einfach und robust.

## ADR-07 Optimistisches Locking gegen unbemerktes Überschreiben

`BacklogItem.version` wird bei jeder Änderung erhöht. Board-Karten und
Bearbeitungsformulare senden die geladene Version mit. Weicht sie ab, wird
nichts gespeichert: Board-Endpunkt → HTTP 409 mit aktuellem Stand (die Karte
springt zurück und eine Meldung erscheint), Formular → 409 mit aktuellen Werten.

## ADR-08 Sprint-Historie über `SprintItem.outcome`

Jede Zuordnung eines Eintrags zu einem Sprint ist ein `SprintItem` mit
Ergebnis (`open`, `completed`, `carried_over`, `returned`, `removed`,
`cancelled`) sowie Status und Story Points zum Abschlusszeitpunkt. Beim
Abschluss wird nicht erledigte Arbeit entweder in einen geplanten Folgesprint
übernommen (neuer `SprintItem`) oder zurück ins Product Backlog gegeben – der
abgeschlossene Sprint behält seine vollständige Historie. Ein Eintrag kann
gleichzeitig nur in einem offenen Sprint sein.

## ADR-09 Ein aktiver Sprint pro Projekt – doppelt abgesichert

Service-Prüfung in `start_sprint` plus partieller DB-Unique-Constraint
`UNIQUE(project) WHERE status = 'active'`. Sprintlänge maximal 31 Tage
(Scrum: höchstens ein Monat), Enddatum ≥ Startdatum (Check-Constraint).

## ADR-10 Agile Board: Drag & Drop mit progressiver Verbesserung

Jede Karte enthält ein normales Formular (Status-Auswahl + „Verschieben“),
das ohne JavaScript und per Tastatur funktioniert. `static/js/board.js` ergänzt
natives HTML5-Drag-&-Drop und sendet JSON an denselben Endpunkt
(`board:move`, CSRF-geschützt). Statuswechsel sind nur für Einträge des aktiven
Sprints erlaubt. Abgeschlossene Sprints können schreibgeschützt angezeigt
werden. Klick auf eine Karte öffnet einen Dialog, dessen Inhalt
serverseitig gerendert wird (`?partial=1`); ohne JavaScript führt der Link
zur Detailseite.

## ADR-11 Geschützte Anhänge

Uploads werden mit zufälligem Dateinamen unter `MEDIA_ROOT/attachments/<projekt>/`
gespeichert, Dateiendung gegen eine Positivliste geprüft und auf 10 MB
begrenzt. Es gibt **keine** öffentliche Media-URL; Downloads laufen über
eine View mit Projektrechteprüfung und `Content-Disposition: attachment`.

## ADR-12 Konfiguration und Umgebungen

Kein Fremdpaket für Umgebungsvariablen; `config/env.py` liest Umgebung und
optional `.env`. Getrennte Settings für Entwicklung, Produktion (HTTPS,
sichere Cookies, HSTS, Pflichtprüfungen für Secret Key und Hosts) und Tests.
`ATOMIC_REQUESTS` ist aktiv, damit ein Request vollständig oder gar nicht
gespeichert wird. `LoginRequiredMiddleware` (Django 5.1+) macht alle Seiten
standardmäßig anmeldepflichtig.

## ADR-13 Frontend ohne Build-Schritt

Bootstrap 5.3 liegt lokal in `static/vendor/` (kein externes CDN im internen
Netz). Designvariablen zentral in `static/css/app.css` (`--ab-*`), Komponenten
(Karten, Badges, Tabellen, Board) als wiederverwendbare Klassen; Formulare über
`templates/includes/form_fields.html` und den Filter `bootstrap`.

## ADR-14 Tests gegen PostgreSQL

Constraints und Sperren verhalten sich in PostgreSQL anders als in SQLite;
deshalb laufen alle Tests gegen PostgreSQL. Für Rechner ohne Installation
startet `scripts/run_with_pg.py` ein eingebettetes PostgreSQL (`pgserver`).

## ADR-15 Burndown aus der Statushistorie rekonstruiert

Statt eines täglichen Snapshot-Jobs berechnet `apps/reporting/burndown.py` die
Restpunkte je Sprinttag aus den `status`-Einträgen des Änderungsprotokolls und
dem Zeitpunkt, zu dem ein Eintrag dem Sprint zugeordnet wurde (`SprintItem.added_at`).
Einträge, die vor dem Sprintstart zugeordnet wurden, zählen ab dem ersten Tag;
später ergänzte Einträge erhöhen die Restpunkte ab ihrem Zuordnungstag.
Abgeschlossene Sprints nutzen die eingefrorenen `points_at_close`. Das
Diagramm wird serverseitig als SVG gerendert (keine Chart-Bibliothek, keine
externen Abhängigkeiten) und ist zusätzlich als Tabelle verfügbar.

## ADR-16 Live-Board per Polling

Das Board fragt im Intervall `BOARD_POLL_INTERVAL_SECONDS` den Endpunkt
`board:state` ab. Dieser liefert nur eine Revision (Hash aus Sprint und
Nummer/Status/Version aller Sprint-Einträge). Weicht sie ab, lädt das Board
die eigene Seite neu und ersetzt den Board-Inhalt; während eines Drag-Vorgangs
und in verborgenen Tabs wird nicht abgefragt. Polling funktioniert unter WSGI
ohne Channels/Redis; WebSockets lohnen sich erst bei deutlich mehr
gleichzeitigen Nutzern. Das optimistische Locking (ADR-07) bleibt als Schutz
bestehen.

## ADR-17 Login-Sperre in der Datenbank

Fehlgeschlagene Anmeldungen werden als `AuthAttempt` gespeichert. Nach
`LOGIN_FAILURE_LIMIT` Fehlversuchen je Benutzername bzw.
`LOGIN_IP_FAILURE_LIMIT` je IP innerhalb von `LOGIN_LOCKOUT_MINUTES` wird
die Anmeldung gesperrt, auch bei korrektem Passwort. Die Speicherung in
PostgreSQL wirkt über mehrere Worker-Prozesse hinweg, ohne Cache-Server oder
Fremdpaket. Dieselbe Prüfung gilt für den Admin-Login. Passwort-Reset-Anfragen
werden je IP und Stunde begrenzt; die Antwortseite verrät nicht, ob ein Konto
existiert. `X-Forwarded-For` wird nur mit `TRUST_X_FORWARDED_FOR` ausgewertet.

## ADR-18 E-Mail-Benachrichtigungen nach dem Commit

Die App `notifications` rendert Nachrichten sofort und versendet sie über
`transaction.on_commit`. Wird eine Aktion zurückgerollt, geht keine E-Mail
hinaus. Versandfehler werden protokolliert und brechen die fachliche Aktion
nicht ab. Benachrichtigt werden nur aktive Konten mit E-Mail-Adresse und
aktivierter Option `email_notifications`; der Auslöser selbst erhält keine
Nachricht. Links basieren auf `SITE_URL` (Produktion: HTTPS-Pflicht).

## ADR-19 Virenprüfung mit ClamAV, standardmäßig fail-closed

`apps/backlog/scanning.py` sendet Uploads per `INSTREAM`-Protokoll direkt an
`clamd` (Socket, keine zusätzliche Bibliothek). Infizierte Dateien werden
abgelehnt und protokolliert. Ist der Dienst nicht erreichbar, werden Uploads
abgelehnt (`ATTACHMENT_SCAN_FAIL_CLOSED=true`); fail-open ist nur bewusst
konfigurierbar. In Produktion ist `clamav` der Standard, in Entwicklung und
Tests ist die Prüfung abgeschaltet.
## ADR-20 Designsystem „Dark Neon“ mit Hell/Dunkel und Animationen

Das Aussehen wird vollständig über CSS-Variablen in `static/css/app.css`
gesteuert (`[data-theme="dark"]` und `[data-theme="light"]`); die
Klassen der Templates bleiben unverändert. `static/js/theme.js` wird
synchron im `<head>` geladen, setzt das gespeicherte bzw. vom System
bevorzugte Farbschema vor dem ersten Rendern (kein Aufflackern) und
aktiviert Animationen nur ohne „Bewegung reduzieren“. `static/js/effects.js`
ergänzt progressiv: Partikelhintergrund (pausiert in inaktiven Tabs),
hochzählende Kennzahlen, Lichtkegel/3D-Neigung, Klick-Wellen und den
Theme-Wechsel per View Transition. Seitenwechsel nutzen die
Cross-Document View Transitions des Browsers. Eintrittsanimationen
verwenden `animation-fill-mode: backwards`, sodass Inhalte auch ohne
JavaScript sichtbar sind. Die Navigationsleiste bleibt in beiden Modi dunkel,
damit das weiße Original-Logo lesbar ist. Keine externen Schriften,
Bibliotheken oder CDNs.

Die Navigation ist eine schwebende Glas-Leiste oben (`templates/base.html`,
`static/js/nav.js`): Logo links, Bereiche als Pille in der Mitte, Profil-Menü
rechts. Ein Leucht-Indikator gleitet zum aktiven bzw. überfahrenen Punkt und
merkt sich seine Position über Seitenwechsel (sessionStorage). Ohne
JavaScript ist der aktive Punkt per Hintergrund markiert (`aria-current`).
Unter 1400 px zeigen nur der aktive Punkt Text und die übrigen Symbole;
unter 992 px klappt die Navigation in ein Menü hinter einem Knopf.

## ADR-21 Wählbares Design je Benutzer (Neon/Patina) als CSS-Schicht

Zwei Teams haben unterschiedliche Oberflächen entworfen; jeder Mitarbeiter
soll sein Design wählen können, ohne dass Funktionen auseinanderlaufen.
Entscheidung: Es gibt genau ein Markup (gemeinsame Templates) und ein
gemeinsames Stylesheet `app.css` für Layout und Neon. Das Patina-Design ist
eine Zusatzschicht `patina.css`, deren Regeln ausschließlich unter
`html[data-design="patina"]` greifen und nur Farben, Flächen, Buttons,
Badges, Kopfleiste und Board überschreiben. Neue Funktionen müssen deshalb
nur einmal gebaut werden und funktionieren in beiden Designs.

Die Wahl liegt im Konto (`User.design`, Standard `neon`), damit sie auf allen
Geräten gilt; umgeschaltet wird per POST (`accounts:design`) aus dem
Benutzermenü oder im Profil. `base.html` setzt `data-design` serverseitig und
lädt nur die Dateien des gewählten Designs: Neon nutzt `theme.js`
(Hell/Dunkel-Schalter), Patina `patina-theme.js` (stufenloser Regler, der
Flächen- und Textfarben fließend mischt). Neon-Partikel werden bei Patina
nicht gestartet, die Drag-Spur nur für Patina geladen. Die Kopfleiste bleibt
in beiden Designs dunkel, damit das weiße Logo lesbar ist. Anmeldeseiten
nutzen immer Neon, da dort noch kein Benutzer bekannt ist.