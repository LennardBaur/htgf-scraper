# Hey Nico,

danke für die Case Study, hat richtig Spaß gemacht und ich hoffe das Ergebnis gefällt dir. Hier ist die Anleitung, wie du alles zum Laufen bekommst, plus ein bisschen Kontext zur Vorgehensweise. Falls etwas nicht klappen sollte, schreib mir doch gerne nochmal eine E-Mail. 

## TL;DR

Ich hab einen Sourcing-Agent gebaut, der pre-seed / seed Digital-Tech Startups hauptsächlich im DACH Raum findet (vorerst, ist jederzeit anpassbar auf die ganze Welt). Drei Datenquellen sind live, vier sind implementiert aber deaktiviert (mehr dazu unten). Alle Gewichte, Auswertungen und konkrete Wünsche könnten immer so angepasst werden, wir ihr das möchtet.

**Ergebnis im Repo:** 46 angereicherte Startups, gerankt nach HTGF Fit, plus 46 deutsche One-Pager. Der ganze Pipeline-Lauf hat 3,07 $ gekostet.

---

## Wie du das ausprobierst

Meine ge-scrapten Daten findest du an sich hier im repo, da ich die Ergebnisse mit gepusht habe, unter /outputs. Dort gibt es one-pager, oder auch eine excel liste, die automatisch erstellt werden nach jedem scraping. Außerden wird alles gleichzeitig in eine google excel eingepflegt (https://docs.google.com/spreadsheets/d/1y0MakVpNVn2HOBFIQeLZTdttoQSWASid_2y1NdJxQmk/edit?usp=sharing). Ansonsten kannst du den Prozess gerne selber starten mit zwei Arten: 

Du brauchst nur `uv` installiert haben (quasi wie `pip` und `venv`)

```bash
brew install uv                                    # Mac
curl -LsSf https://astral.sh/uv/install.sh | sh    # Linux / WSL
```
Mit Windows kenne ich mich leider nicht extrem gut aus, daher müsste man da schauen. Habe diese Doku gefunden (https://docs.astral.sh/uv/getting-started/installation/)

Den Rest macht das Repo.

### Variante 1 — nur anschauen (re-run meines crawls)

```bash
uv sync
uv run sourcer export
```

Kein API-Key. Kein Netzwerk. 0 $. Das regeneriert die Outputs aus dem Cache, der im Repo liegt. Dann öffne in dieser Reihenfolge:

1. **`outputs/run_summary.md`** — Statistik vom Run plus Top-5 mit direkten Links
2. **`outputs/leads.xlsx`** — die zentrale Tabelle (frozen header, sortierbar)
3. Ein, zwei One-Pager aus **`outputs/onepagers/`** — pro Startup ein deutsches Briefing

### Variante 2 — Pipeline frisch laufen lassen

Wenn du sehen willst, was *heute* gefunden wird:

```bash
cp .env.example .env       # mindestens ANTHROPIC_API_KEY rein
uv run sourcer run-all --max-spend 5
```

`--max-spend 5` ist eine harte Obergrenze für den Run — falls irgendwas durchdreht, wird sauber bei 5 $ abgebrochen. Der Original-Run hat ~3 $ gekostet, also bequemer Puffer.

Die anderen API-Keys (GitHub, Product Hunt, Firecrawl) sind nice-to-have. Ohne sie laufen die jeweiligen Collectors degraded, aber nicht gar nicht.

### API-Key-Situation

Einfach ein .env file erstellen, ich schicke dir einen Yopass link mit allen API keys bzw. dem ganzen file das du rauskopieren kannst und einfügen. 

## Architektur in einem Bild

Drei Stages, jede idempotent, jede über SQLite gestated:

```
DISCOVER  →  ENRICH  →  SCORE & EXPORT
```

Im Folgenden was hinter jedem Pfeil passiert.

---

## Was konkret passiert, Schritt für Schritt

### 1. Drei Quellen anzapfen

Das Tool holt sich Leads parallel aus drei APIs. Jede Quelle hat einen eigenen Filter, der schon vor dem teuren LLM-Schritt aussortiert was offensichtlich nicht passt:

**Hacker News** — alle "Show HN" Posts der letzten 90 Tage über die Algolia-API. Das sind etwa 300 Stück. Damit nicht jeder einzeln teuer durch Sonnet läuft, geht erst ein billiger **Claude Haiku** als Vorfilter drüber mit der Frage: *"Ist das ein DACH-basiertes B2B-SaaS, Dev-Tool oder AI-Produkt?"* — Antwort Ja oder Unsicher landet in der DB, Nein wird verworfen. **Ergebnis: 26 Leads.** -> Hier kann man natürlich filtern wie wir wollen am Ende

**Product Hunt** — alle Launches der letzten 90 Tage mit mindestens 10 Upvotes über die GraphQL-API. Hier kein Geo-Filter beim Discover, weil PH keine zuverlässigen Standort-Infos zu Makern liefert. Globalen Pool sammeln, der Scoring-Prompt am Ende sortiert dann nicht-DACH-Firmen über die `thesis_fit`-Dimension nach unten. **Ergebnis: 15 Leads.**

**GitHub** — Suche nach Usern mit Location-Tag *"Germany / Berlin / Munich / Austria / Vienna / Switzerland / Zurich"*, dann deren neueste original Repos (keine Forks, mindestens 10 Stars). Mein erster Plan — Repos suchen und nach `.de`-Homepage filtern — hat 0 echte DACH-Startups gefunden, weil die alle `.com` / `.ai` / `.io` für internationale Märkte nutzen. Der Pivot zur User-Suche steht im Commit-Log. **Ergebnis: 5 Leads.** -> Auch hier kann alles angepasst werden, also Weltweite Suche etc.

Macht **46 unique Leads** insgesamt (nach Dedup über die normalisierte Domain).

### 2. Alles in einer SQLite-Datenbank speichern

Jeder Lead landet als Zeile in `cache/state.db`, gehashed über die normalisierte Domain (lower-case, kein `www.`, kein trailing slash, keine `utm_*` Parameter). Wenn die gleiche Firma in zwei Quellen auftaucht — z.B. einmal in HN und einmal in PH — werden die Einträge transparent zusammengeführt. Im finalen Output siehst du dann unter der `sources`-Spalte alle Quellen, in denen sie aufgetaucht ist. **Multi-Source-Coverage ist selbst ein positives Signal** — was an mehreren Stellen Spuren hinterlässt, ist meistens relevanter.

### 3. Jeden Lead anreichern

Für jeden Lead, der noch nicht angereichert ist (oder älter als 14 Tage):

- Hole die Landing-Page plus typische Subseiten parallel: `/about`, `/team`, `/ueber-uns`, `/about-us`
- Dafür gibt es eine **Fetch-Kette mit drei Ebenen**: erst **Jina Reader** (kostenlos, liefert sauberes Markdown für ~80% der URLs), dann **Firecrawl** als Fallback (kostet ~$0.005/Seite, aber zuverlässiger bei JS-heavy Sites), dann **Playwright headless** als letzte Bastion (für Cloudflare-geschützte Seiten)
- Das gesammelte Markdown geht an **Claude Sonnet 4.6** mit einem Pydantic-Schema. Sonnet gibt ein validiertes Objekt zurück mit: Name, One-Liner, Sektor, Stadt + Land, Gründungsjahr, Stage-Signal, Gründer (Name + Rolle + LinkedIn + E-Mail wenn auf der Seite gelistet), Traction-Signale, Funding-Signale

Wichtig zum Datenschutz: Bei E-Mails ist der Prompt strikt, die werden **nur** übernommen wenn sie explizit im Impressum oder auf der Kontaktseite stehen. Nichts wird geraten, nichts aus Namen abgeleitet. Tests prüfen das.

### 4. Bewerten gegen HTGF's Thesis

Jedes angereicherte Startup geht durch einen zweiten Sonnet-Call mit dem Scoring-Prompt. Im Prompt sind **fünf echte HTGF Portfolio-Companies als positive Anker** (Zeeg, Stackgini, Pactos, syte, Data Virtuality) und **vier negative Anker** (Consumer-Apps ohne Enterprise-Angle, Hardware-only, Late-Stage, non-DACH). Damit biased Sonnet nicht zu generischem "B2B SaaS gut" sondern zu eurem tatsächlichen Investmentstil.

Bewertet werden fünf Dimensionen, jede 1–5:

| Dimension | Gewicht | Was reinzählt |
|---|---:|---|
| `thesis_fit` | 35 % | B2B SaaS? AI-native? DACH? Passt zum HTGF-Profil? |
| `earliness` | 25 % | Wie früh sind wir dran? 5 = noch in Stealth, 1 = schon mit Tier-1 Lead |
| `team_quality` | 20 % | Technische Gründer? Akademische / Exit-Vorgeschichte? Multi-Founder? |
| `traction` | 15 % | Zahlende Kunden? GitHub-Momentum? Bekannte Partner? |
| `contactability` | 5 % | LinkedIn / E-Mail überhaupt vorhanden? |

Plus eine deutsche Begründung in 2-3 Sätzen und eine Liste expliziter Red Flags. Der gewichtete `overall` Score ist die Sortier-Reihenfolge im finalen Output. Weights liegen in `config/htgf_thesis.yaml` und sind ohne neuen LLM-Call änderbar — `sourcer score` läuft gegen den Cache.

### 5. Schreiben

Alles wird zusammengeführt, nach `overall` gerankt, und exportiert:

- **`outputs/leads.csv`** und **`.xlsx`** — die zentrale Tabelle, eine Zeile pro Startup, 30 Spalten
- **`outputs/onepagers/01_*.md`** bis **`46_*.md`** — ein deutsches Briefing pro Startup mit Rationale, Gründern, Quellen
- **`outputs/run_summary.md`** — Statistik, Top-5, Kosten, Lauf-Zeit
- ** Google Sheet mit datiertem Tab pro Run (überspring-bar mit `--no-sheets`)

### Caching, damit es nicht jedes Mal kostet

Jede gefetchede Seite und jeder LLM-Call ist Hash-keyed und auf Disk gespeichert (`cache/state.db`, `cache/pages/`). Beim zweiten Run ist alles was sich nicht geändert hat gratis — gleicher Input gibt gleichen Output. Deshalb kannst du die ganze Pipeline ohne API-Key replay: der Cache liegt im Repo.

---

## Was AI-native an dem Ganzen ist

1. **Null CSS-Selektoren im ganzen Repo.** Jede Seite läuft durch Jina Reader → Markdown → Claude mit Pydantic-getriebenem Tool-Use. Wenn ihr morgen ein neues TTO dazuwollt, ist das eine YAML-Zeile, kein Refactor.
2. **HTGF-Anker im Score-Prompt**  Bias zu eurem tatsächlichen Stil statt zu generischem "B2B SaaS gut".
3. **Pydantic-Schemas → Tool-Use Schemas.** `model.model_json_schema()` füttert Anthropic direkt. Wenn ich morgen ein Feld zur Datenstruktur hinzufüge, weiß der LLM-Vertrag automatisch davon. Kein Drift zwischen Code und Prompt.

---

## Was nicht funktioniert hat

Vier von sieben Quellen sind implementiert, getestet, aber per Config deaktiviert.

- **EXIST-Liste** ist mittlerweile eine Marketing-Landingpage. Die echten Projekt-Einträge sind in Sub-Seiten pro Förderprogramm gewandert.
- **TUM- und RWTH-Spin-out-URLs** geben 404. Die noch lebenden TTO-Seiten beschreiben Programme, keine konkreten Ausgründungen.
- **Beta List** `/markets/germany` ist ein Kategorie-Index ("AI", "Commerce"), keine Startup-Liste.
- **Handelsregister** über OffeneRegister ist zu sparse — das `purpose` Feld ist bei den meisten Einträgen leer.

Ich hab das bewusst deaktiviert, aus drei Gründen:

- Jede fehlgeschlagene Extraktion verbrennt LLM-Budget für nichts
- Ein still scheiternder Collector im Run wäre für den nächsten Analysten unklarer als ein expliziter Toggle in `config/sources.yaml`
- Die richtigen Lösungen sind per-Programm-Crawler bei EXIST und die Northdata-API fürs Handelsregister — beides ist v2-Material, nicht v1-Hackery

Im `config/sources.yaml` ist jede deaktivierte Quelle mit Begründung markiert. Tests laufen über alle sieben, damit der Code nicht verrottet wenn die Quellen wieder erreichbar werden.

---

## Stack

Bewusst lean gehalten: `uv` · Python 3.11 · `httpx` (async) · `selectolax` · Playwright (nur als Fallback) · Anthropic SDK direkt (kein LangChain) · Claude Sonnet 4.6 für Extraktion + Scoring · Claude Haiku 4.5 für HN-Filter und pairwise Dedup · Pydantic v2 mit Tool-Use · SQLite (stdlib) · Typer / Loguru / Rich · pandas + openpyxl · gspread für Sheets · pytest mit 80 Tests, alle mocked, läuft in ~1,2 Sekunden.

Keine Dependency, die nicht arbeitet.

## Wie würde ich weitermachen

- **Daily Cron** über GitHub Actions, Slack-Nachricht ab Score-Schwelle
- **Per-Programm-Crawler** für EXIST — jedes Förderprogramm hat eine eigene Sub-Seite die mit Link angepasst werden müsste
- **Northdata-API** für Handelsregister-Sourcing (kostet)
- **Proxycurl** für LinkedIn-Anreicherung — würde die `contactability`-Dimension besser machen denke ich
- **Embedding-Dedup** ab dem Punkt, wo > 1000 Startups in der DB sind (Haiku pairwise skaliert nicht ewig)
- **Streamlit-Dashboard** über die gleiche SQLite, für Leute die keine CLI mögen :) 
