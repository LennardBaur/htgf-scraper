# iasql

**Rang:** 13 / 31   **Score:** 2.70 / 5.00

| | |
|---|---|
| Website | [https://feers77.github.io/iasql](https://feers77.github.io/iasql) |
| Sitz | — |
| Gegründet | — |
| Stage | Pre-Launch |
| Sektor | DevTools · AI / Knowledge Infrastructure |

## In einem Satz
A PostgreSQL extension that turns your database into a self-compiling, LLM-powered knowledge base with built-in hallucination auditing.

## Was sie machen
iasql is an open-source PostgreSQL extension implementing Andrej Karpathy's "LLM Wiki" pattern entirely inside the database engine. Users INSERT raw documents into an append-only ground-truth layer; a background worker asynchronously dispatches them to any OpenAI-compatible LLM (Ollama, llama.cpp, vLLM, OpenAI, etc.), which compiles them into a maintained, cross-referenced Markdown wiki stored in compiled_pages and an entity_graph. A nightly pg_cron job audits the compiled wiki against the original sources and flags potential hallucinations. Unlike RAG systems that re-discover domain knowledge on every query, iasql accumulates understanding at ingest time, letting knowledge compound across documents. The compiler and auditor system prompts are exposed as live-tunable PostgreSQL GUCs, making the entire knowledge pipeline configurable without restarting the database. The project is at version 0.1 — a working proof of concept built and tested on PostgreSQL 17, with a live wiki demo and a landing page hosted on GitHub Pages.

## Gründer
- **feers77** — Creator / Author
  - LinkedIn: —
  - E-Mail: —
  - Hintergrund: GitHub username feers77; Spanish-speaking developer (README available in Spanish); built and maintains iasql

## Traction
- Version 0.1 working proof of concept on PostgreSQL 17
- Live wiki demo at https://iasql.dev.feres.cl
- Public GitHub repository at https://github.com/feers77/iasql
- Tutorial documentation published

## Finanzierung
—

## Bewertung (LLM)

| Dimension | Score |
|---|---|
| Thesis-Fit | 3/5 |
| Team-Qualität | 1/5 |
| Frühphasen-Vorteil | 5/5 |
| Traction | 1/5 |
| Erreichbarkeit | 1/5 |

**Begründung:** iasql adressiert einen interessanten DevTools-/AI-Infrastruktur-Anwendungsfall (LLM-gestützte Wissensdatenbank als PostgreSQL-Extension), der thematisch zum HTGF-Digital-Tech-Fokus passt – allerdings fehlt ein klarer B2B-SaaS-Ansatz mit Monetarisierungsstrategie, und das Projekt ist derzeit rein open-source auf Proof-of-Concept-Niveau (v0.1). Der einzige bekannte Gründer tritt nur unter einem GitHub-Pseudonym auf, spricht offenbar Spanisch und weist keinen DACH-Bezug auf; weder Unternehmensregistrierung noch Standort noch Team sind verifizierbar. Angesichts der fehlenden geografischen Verankerung in Deutschland/DACH, der völligen Intransparenz des Teams und des Fehlens jeglicher kommerzieller Signale ist ein Investment zum aktuellen Zeitpunkt nicht begründbar.

**Red Flags:**
- Kein DACH-Bezug: HQ-Land und -Stadt unbekannt, Gründer vermutlich nicht in Deutschland ansässig (spanischsprachig, .cl-Domain)
- Gründer nur als GitHub-Pseudonym 'feers77' bekannt – kein echter Name, kein LinkedIn, keine E-Mail
- Keine Unternehmensregistrierung, kein Gründungsjahr, kein nachweisbares Team
- Rein open-source, v0.1 Proof of Concept – kein Geschäftsmodell oder Monetarisierungsstrategie erkennbar
- Keine Paying Customers, keine Partnerships, keine kommerziellen Traction-Signale
- Namenskonflikt: 'iasql' ist bereits ein bekanntes, eingestelltes Open-Source-Projekt (IaSQL, Infrastructure-as-SQL) – mögliche Marken-/Reputationsrisiken

## Quellen
- https://github.com/feers77/iasql
- https://github.com/about
- https://github.com/about-us
- https://github.com/team
- https://github.com/ueber-uns
- https://github.com/uber-uns
- https://github.com/jobs
- https://github.com/careers

---
*Generiert am 2026-05-25 · canonical_id: `be6c08258f5a59c263ba8955f8e0d53f623cda38720eaabc16d5d16469309a43`*
