# Known limits: unresolved Calls

FACT — Diagnose zu Pledge `9919bdd8c50d84b37c19a4d6047d85d726892c0e`; keine Änderung am Resolver.
FACT — EE-Producer: `dc7526592073985ed69902b21d6a1c861ac02fa0`.
FACT — Frischer Clone: `make check PRODUCER_ROOT="$PRODUCER_ROOT"`, Exit 0, 197 Tests einschließlich D-self.

## Methode und Quellen

FACT — Gezählt werden Call-Records mit `data.status == "unresolved"`, einmal je Record-ID; keine Laufzeithäufigkeiten. Anteile in den Mustertabellen beziehen sich auf alle unresolved Calls des jeweiligen Reports und sind auf zwei Nachkommastellen gerundet.
FACT — Zuordnung zum AST über Datei, Startzeile, Endzeile, Spalte und `ast.unparse(call.func) == data.expression`; verschachtelte Calls können dieselbe Startposition haben. Alle Records sind eindeutig zugeordnet: 234/234 und 1512/1512, keine Restklasse UNKNOWN.
FACT — Ein Muster ist die unmittelbare AST-Form von `Call.func`, bei `Attribute` zusätzlich dessen `value`. Die Klassen sind disjunkt. `x.m()` behauptet keinen Receiver-Typ; Protocol-Parameter, lokale Container und andere Namen sind darin zusammengefasst.
FACT — Source-Digests der beiden Reports stimmen mit den gelesenen Dateien überein. Der D-self-Test reobserviert den Clone und vergleicht die gespeicherte Coverage (`tests/test_self.py:51`).
FACT — D-self-Quelle: `fixtures/D-self/architecture.json` (Python 3.11.12). Repo-2-Quelle: `$REPO2_REPORT` (Python 3.12.10), Root `$REPO2_ROOT`.

| FACT: Provenienz | D-self | Repo #2 |
|---|---|---|
| Source-Digest | `fcc8bb98c201745f4f2e1a5c7be5aad36033abdaab221afe65df9a966224e3f6` | `343d8ed481ab932b65660131132fe1d80f74b8939a0e922b555614775419d674` |
| Report-SHA256 | `274b90a96aec2d6ebe0dec055c528f063d49d8b5e67fd7ad199166ae665808a2` | `5757b27b6a3ec020270f65a7411a0c3f06324586ef9f5d7f2f78d4bbe216cb81` |

FACT — Reproduktionsskript und vollständige Zuordnung jeder Call-ID: `$DIAGNOSTICS/classify_calls.py`, `self-analysis.json`, `repo2-analysis.json`. Das Skript prüft Source-Digest, Parser-Version und Zuordnung; Exit 0 unter der jeweiligen Producer-Python-Version. Diese lokalen Diagnoseartefakte sind nicht Teil des Commits.

## D-self

FACT — 28 Dateien vollständig geparst; `calls_total = 1318`; unresolved `234/1318 = 17,75 %`.

| FACT: Rang / syntaktisches Muster | Anzahl | Anteil an unresolved | Zitat + Datei:Zeile |
|---|---:|---:|---|
| 1. Methode auf Namen: `x.m()` (`Attribute(Name)`) | 157 | 67,09 % | `value.decode()` — `src/pledge/check/git.py:47` |
| 2. Methode auf Call-Ergebnis: `f().m()` (`Attribute(Call)`) | 31 | 13,25 % | `render_result(result).decode()` — `src/pledge/cli/__init__.py:98` |
| 3. Direkter Namensaufruf: `f()` (`Name`) | 18 | 7,69 % | `producer(` — `src/pledge/check/run.py:158` |
| 4. Methode auf Attribut: `x.y.m()` (`Attribute(Attribute)`) | 9 | 3,85 % | `path.parent.mkdir(parents=True, exist_ok=True)` — `src/pledge/check/report.py:56` |
| 5. Methode auf indiziertem Wert: `x[k].m()` (`Attribute(Subscript)`) | 8 | 3,42 % | `entries[0][0].split()` — `src/pledge/check/git.py:39` |

FACT — Top-5 zusammen: 223/234 = 95,30 %. Rest vollständig aufgeschlüsselt:

| FACT: Weitere AST-Form | Anzahl | Anteil an unresolved |
|---|---:|---:|
| Methode auf Literal (`Attribute(Constant)`) | 5 | 2,14 % |
| Methode auf binärem Ausdruck (`Attribute(BinOp)`) | 4 | 1,71 % |
| Methode auf Dict-Literal (`Attribute(Dict)`) | 1 | 0,43 % |
| Methode auf Set-Literal (`Attribute(Set)`) | 1 | 0,43 % |

## Repo #2

FACT — 74 Dateien vollständig geparst; `calls_total = 6368`; unresolved `1512/6368 = 23,74 %`.

| FACT: Rang / syntaktisches Muster | Anzahl | Anteil an unresolved | Zitat + Datei:Zeile |
|---|---:|---:|---|
| 1. Methode auf Call-Ergebnis: `f().m()` (`Attribute(Call)`) | 622 | 41,14 % | `select(MandantModel).where(MandantModel.id == mandant)` — `backend/services/customer_portal.py:111` |
| 2. Methode auf Namen: `x.m()` (`Attribute(Name)`) | 515 | 34,06 % | `statement.where(PlanungslaufModel.typ == typ.value)` — `backend/services/disposition_queries.py:550` |
| 3. Methode auf Await-Ergebnis: `(await f()).m()` (`Attribute(Await)`) | 217 | 14,35 % | `(await session.execute(order_query)).scalars()` — `backend/services/mobile_sync.py:157` |
| 4. Methode auf Attribut: `x.y.m()` (`Attribute(Attribute)`) | 98 | 6,48 % | `uow.session.flush()` — `backend/services/disposition_commands.py:897` |
| 5. Direkter Namensaufruf: `f()` (`Name`) | 28 | 1,85 % | `callback(message)` — `backend/orchestrator/handlers.py:69` |

FACT — Top-5 zusammen: 1480/1512 = 97,88 %. Rest vollständig aufgeschlüsselt:

| FACT: Weitere AST-Form | Anzahl | Anteil an unresolved |
|---|---:|---:|
| Methode auf indiziertem Wert: `x[k].m()` (`Attribute(Subscript)`) | 10 | 0,66 % |
| Methode auf f-String (`Attribute(JoinedStr)`) | 8 | 0,53 % |
| Methode auf Literal (`Attribute(Constant)`) | 7 | 0,46 % |
| Methode auf binärem Ausdruck (`Attribute(BinOp)`) | 3 | 0,20 % |
| Methode auf Dict-Literal (`Attribute(Dict)`) | 2 | 0,13 % |
| Methode auf booleschem Ausdruck (`Attribute(BoolOp)`) | 2 | 0,13 % |

## Vergleich und Resolver-Grenze

FACT — Nein, die Top-5 sind nicht identisch. Vier Formen überlappen: `Attribute(Name)`, `Attribute(Call)`, `Attribute(Attribute)`, `Name`. D-self hat zusätzlich `Attribute(Subscript)` (8); Repo #2 stattdessen `Attribute(Await)` (217). Await-Receiver: D-self 0. Subscript-Receiver: Repo #2 10, außerhalb seiner Top-5.
FACT — Gemeinsame Scanner-Grenzen: `_resolve` prüft indizierte Namen, Import-Aliase, Builtins und einfache Attributketten. Argument-Annotationen, lokale Zuweisungen und Rückgabetypen gehen dort nicht ein (`script/architecture/scanner.py:573–618` im EE-Producer).
FACT — Getrennt sichtbar: D-self wird von `x.m()` geprägt (157/234); in Repo #2 liegen Call- und Await-Ergebnisse vorn (622 + 217 = 839/1512). Die Beispiele zeigen Query-Verkettung und asynchrone Resultate; eine pauschale Gleichsetzung aller 839 Calls mit SQL wäre unbelegt.
FACT — Die Report-Gründe lassen sich vollständig mit den Resolver-Zweigen abgleichen:

| FACT: Report-Grund | D-self | Repo #2 | Prüfstelle im EE-Producer |
|---|---:|---:|---|
| `dynamic attribute receiver` | 166 | 613 | `script/architecture/scanner.py:593–617` |
| `call target is a dynamic expression` | 50 | 871 | `script/architecture/scanner.py:486–495`, `:618` |
| `name has no statically indexed binding` | 18 | 28 | `script/architecture/scanner.py:573–591` |

FACT — Ein Call-/Await-/Subscript-/Literal-Receiver scheitert bereits an `_dotted_expression`; `_resolve` liefert dann den Grund `call target is a dynamic expression`. Das ist eine Scanner-Klassifikation, kein Beweis für einen zur Laufzeit unbestimmbaren Aufruf.
FACT — `partially_resolved` ist hier ausgeschlossen: 60 Calls in D-self, 578 in Repo #2. Ein Namensmatch mit internen Methoden kann einen dynamischen Receiver bereits partiell klassifizieren; Import-Alias-Attribute werden direkt als resolved klassifiziert (`script/architecture/scanner.py:595–616`). Die unresolved-Quote allein misst deshalb keine Architekturqualität.

## Offene Aussagen

UNKNOWN — Wie viele Receiver innerhalb `x.m()` Protocols, Dataclasses oder andere konkrete Typen haben; diese Diagnose klassifiziert Syntax, keine Typen.
UNKNOWN — Welche und wie viele Ziele ein erweiterter Resolver korrekt bestimmen könnte; kein alternativer Resolver wurde ausgeführt.
HYPOTHESIS — Die unresolved-Quote könnte mit „Modernität“ des Codes steigen. Zwei verschiedene Repos, Scopes und Python-Versionen belegen keinen solchen Zusammenhang; „Modernität“ wurde nicht operationalisiert.
UNKNOWN — Verfügbarkeit der lokalen Repo-2-/Diagnoseartefakte nach einer Bereinigung von `$DIAGNOSTICS`; sie sind nicht im Commit gesichert.
