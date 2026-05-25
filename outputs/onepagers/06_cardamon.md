# Cardamon

**Rang:** 6 / 46   **Score:** 3.05 / 5.00

| | |
|---|---|
| Website | [https://github.com/dominikhei/cardamon](https://github.com/dominikhei/cardamon) |
| Sitz | — |
| Gegründet | — |
| Stage | Pre-Launch |
| Sektor | DevTools · Observability / Monitoring |

## In einem Satz
Open-source metric auditor for Prometheus that identifies unused metrics and generates drop rules to reduce storage costs.

## Was sie machen
Cardamon is an open-source cleanup tool for Prometheus that cross-references every metric in a Prometheus TSDB against query logs, alerting and recording rules, and Grafana dashboards to identify metrics that are scraped and stored but never actually queried. For each unused metric, Cardamon fetches series count, label cardinality, job, and last-seen timestamp. Results are served via a local web UI where users can explore, filter, and export Prometheus drop relabeling rules — grouping metrics by job and combining names into optimised regexes — to reduce storage, memory, and ingestion costs. It is distributed as a Go CLI tool installable via `go install` and configured through a YAML file.

## Gründer
- **Dominik Hei** — Creator / Author
  - LinkedIn: —
  - E-Mail: —
  - Hintergrund: Go developer; GitHub username: dominikhei

## Traction
- Open-source project hosted on GitHub under dominikhei/cardamon
- CI pipeline active via GitHub Actions
- Demo GIF published in repository

## Finanzierung
—

## Bewertung (LLM)

| Dimension | Score |
|---|---|
| Thesis-Fit | 3/5 |
| Team-Qualität | 2/5 |
| Frühphasen-Vorteil | 5/5 |
| Traction | 2/5 |
| Erreichbarkeit | 1/5 |

**Begründung:** Cardamon adressiert einen realen Pain Point im Observability-/DevTools-Bereich (Prometheus-Kostenoptimierung), der grundsätzlich mit dem HTGF-Fokus auf B2B-DevTools und Infrastruktur kompatibel ist. Allerdings handelt es sich aktuell um ein reines Open-Source-CLI-Projekt ohne erkennbares Unternehmens- oder Monetarisierungskonzept, deutschen Standort oder institutionelles Team. Das Projekt befindet sich in einer sehr frühen, noch nicht inkorporierten Phase mit nur einem erkennbaren Entwickler und keinerlei Enterprise-Traction oder Geschäftsmodell-Signal.

**Red Flags:**
- Kein Unternehmen gegründet – rein privates Open-Source-Projekt ohne Inkorporierung
- Solo-Founder, kein Commercial Co-Founder erkennbar
- Kein DACH-Bezug nachweisbar (Stadt, Land unbekannt)
- Kein Geschäftsmodell oder Monetarisierungsansatz sichtbar
- Keine Kontaktmöglichkeit: weder LinkedIn noch E-Mail verfügbar
- Sehr geringe GitHub-Traction: keine Stars/Forks/Issues in den Signals
- Kein Funding-Signal, kein Investoren-Interesse bisher dokumentiert

## Quellen
- https://github.com/dominikhei/cardamon
- https://github.com/about
- https://github.com/about-us
- https://github.com/team
- https://github.com/ueber-uns
- https://github.com/uber-uns
- https://github.com/jobs
- https://github.com/careers

---
*Generiert am 2026-05-25 · canonical_id: `3276246b83eb5333390d6f136f5c132b292a2bc09e53cf187e241266f1bd1a61`*
