# Typisierte Steuerungslogik und überprüfbare Komponenten-APIs

Status: Designentwurf zur Prüfung. Produktänderungen stehen noch aus.

## Ziel und Abgrenzung

ArchKeel soll seine eigenen Architekturregeln auch für die gemeinsam genutzten
Typen und API-Verantwortlichkeiten durchsetzen. Geschlossene Zustände, Kinds und
Modi erhalten einen gemeinsamen Typ; Projektionen sollen diese Semantik nicht
erneut aus offenen Records rekonstruieren.

Arbeitsannahme zur noch offenen Scope-Frage: Modulnamen, Pfade, Symbolnamen und
JSON-Schlüssel bleiben String-Daten. Das Verbot betrifft String-Steuerungslogik
für geschlossene Domänenwerte. Ein Verbot sämtlicher Parser- und Datenvergleiche
wäre eine andere, erheblich größere Migration.

## Verifizierter Ausgangspunkt

Main: `63437df6734275850838ba1026b276c2f930bf2f`.

[Native Bestandsaufnahme](https://github.com/rapiddweller/archkeel/actions/runs/38906824955):
1.662 erfasste `string_literal_compare`-Konstrukte, keine aktivierte eigene
Verbotsregel, null konfigurierte Verstöße und 919 unaufgelöste Calls.
Diese Zahl zählt Syntaxstellen, nicht automatisch Architekturfehler.

Eine isolierte zusätzliche IR-`boundary_types`-Regel liefert 70 Verstöße sowie
161 Position-, 126 Route- und einen Limit-UNKNOWN-Nachweis. Dazu gehören
bewusste Raw-/Codec-Grenzen und fehlende Typveröffentlichungen. Die pauschale
Aktivierung wäre deshalb keine geprüfte Lösung.

Das unabhängige Astra-Audit bestätigt außerdem einen konkreten Unterschied
zwischen Core und Module-Explorer: Legacy-Prefix-Regeln berücksichtigen im Core
weitere Pakete einer Komponente; der Explorer schreibt diese Semantik teilweise
selbst und kann die Regelzuordnung verlieren. Ein falsches Gesamt-PASS ist damit
nicht belegt.

## Vorgehenswahl

Empfohlen: zuerst die konkrete Dependency-Schnittstelle korrigieren, ihre
beabsichtigten Typen und Grenzen im vorhandenen Target ausdrücken und dann
weitere Domänen mit derselben Regel migrieren. So bleiben Semantik und
Kompatibilität jeweils getrennt überprüfbar.

Eine sofortige globale String-Sperre würde auch legitime Datengrenzen treffen.
Ein breiter Ausnahmeblock für bestehende Komponenten würde die gewünschte
Absicherung hingegen umgehen. Beide Ansätze werden verworfen.

## Klare Verantwortlichkeiten

- **IR-Modell:** besitzt Enum-Vokabular und benannte unveränderliche
  Selektionswerte. Ein gemeinsamer reiner Selektionsmechanismus entscheidet,
  welche Module zu einer Regel gehören.
- **Codec-/Record-Grenze:** übersetzt und validiert externe String-Werte einmal
  zu diesen Typen. Unbekannte Werte werden zurückgewiesen; nachgelagerte
  Verbraucher erfinden keine Defaults für beschädigte Werte.
- **Core:** prüft SourceFacts, Subjects, Vollständigkeit und Receipts und
  entscheidet PASS, FAIL oder UNKNOWN.
- **Report-Projektionen:** verwenden die gemeinsame Selektion und bestehende
  Core-Befunde. Sie definieren keine zweite Matching-Policy.
- **Renderer:** stellt die fertige typisierte Projektion dar.

Für diese Naht werden Parameter- und Rückgabetypen nicht auf `str` oder offene
Mappings abgeschwächt. Benannte Selektionstypen ersetzen den verschachtelten
Positions-Tuple dort, wo er die Bedeutung von Source/Target und Prefix/Exact
versteckt. Modulnamen selbst werden dadurch nicht zu künstlichen Enums.

## Arbeitspakete

### 1. Typisierte gemeinsame Dependency-API — Issue #540

Gemeinsame Enums für Match-Modus und Target-Art. Diese Typen gelten vom
Contract-Modell bis zur gemeinsamen Selektions-API. Record-Verbraucher
dekodieren nicht unabhängig voneinander. Der Explorer verwendet dieselbe
Komponenten-/Modulselektion wie Core.

Die Reproduktion verwendet echte Komponentenlabels, mehrere Pakete und
exact_modules. Alle vier Match-Kombinationen, mehrdeutige Ownership und
Import-Namespace-Nichtausweitung erhalten Kontrollen. Symbol-, Typing- und
allowed_sources-Filter bleiben wirksam.

### 2. Prüfbarer eigener Typ-/API-Contract — Issue #541

Einen unabhängig entworfenen, begrenzten Target für diese Typen und
Signaturen im vorhandenen Architekturmodell deklarieren. Ein auf `str`
abgeschwächter Modus, eine verlorene Ergebnisstruktur und ein Zugriff außerhalb
der veröffentlichten API müssen in nativen Negativproben auffallen.

Vorhandene Boundary-Regeln an den tatsächlich gewollten Nähten aktivieren,
benötigte DTO-Typen veröffentlichen und bewusste Codec-Eingänge genau benennen.
Kein globaler IR-Ausnahmeblock und keine pauschale DTO-Pflicht für sinnvolle
generische Algorithmen.

Die vollständige unabhängige Binnenarchitektur aus #340 bleibt ein größeres
eigenes Thema. Strukturelle Protocol-Konformität aus #356 wird hier nicht
nebenbei neu entwickelt.

### 3. String-Steuerungslogik migrieren und sperren — Issue #542

Die Syntaxfundstellen nach Domänensteuerung und Datenverarbeitung trennen.
Für migrierte Domänen die vorhandene `forbidden_construct`-Regel aktivieren.
Neue Final-Strings dürfen die Regel nicht umgehen; echte Enums werden akzeptiert.
Ausnahmen bleiben an der zuständigen Wire-/Parser-Grenze nachvollziehbar.

Kein zweiter Linter und keine neue parallele Policy-Engine. Die Absicherung
wird pro fertig migriertem Scope angegeben; bis zum Abschluss aller betroffenen
Domänen wird keine globale String-Freiheit behauptet.

## Verifikation und Kompatibilität

1. Reale Reproduktion vor der Korrektur, anschließend positiver und negativer
   nativer Nachweis; kein bloßer Snapshot der Contract-Datei.
2. Root-/Mounted-Scope, mehrere Pakete und echte Labels abdecken.
3. Schema 3.4/3.5, strikte Grammatik, ausgelassene Defaults und alte
   Canonical-Bytes/Digests erhalten.
4. Abwesender Target-Namespace: PASS/FAIL nur mit bewiesener Source;
   fehlende oder unvollständige Source bleibt UNKNOWN.
5. Bestehende Typing-, Symbol-, Ausnahme- und Report-Regressionsprüfungen erhalten.
6. Keine erhöhten UNKNOWN-, Coupling- oder Unresolved-Call-Budgets zur
   Herstellung eines grünen Ergebnisses; keine zusätzlichen Casts, Reflection
   oder Hygiene-Ausnahmen.
7. Selektion einmal aufbereiten, keine erneute Policy-Dekodierung pro
   Matrix-Zelle.
8. Je Arbeitspaket separater PR, unabhängiges finales Astra-Review und
   Pflichtprüfungen; anschließend Integration in der notwendigen Reihenfolge.

## Grenzen der Aussage

Eine Dependency-Erlaubnis beweist keine strukturelle Protocol-Konformität.
Prosa-Verantwortlichkeiten und fachliche Gleichwertigkeit werden nicht allein
durch Importregeln bewiesen. Native Mutationsproben müssen zeigen, welcher
Teil der beabsichtigten Typ-/API-Grenze tatsächlich durchgesetzt wird.

Die 70 IR-Probeverstöße werden vor einer Policy-Änderung klassifiziert. Sie
werden weder pauschal freigegeben noch sämtlich als fehlerhafte DTOs behandelt.
