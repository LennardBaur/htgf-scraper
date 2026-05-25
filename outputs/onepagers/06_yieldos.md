# YieldOS

**Rang:** 6 / 31   **Score:** 2.85 / 5.00

| | |
|---|---|
| Website | [https://github.com/nikitph/yieldos](https://github.com/nikitph/yieldos) |
| Sitz | — |
| Gegründet | — |
| Stage | Pre-Seed |
| Sektor | AI Infrastructure · LLM Inference / MLOps |

## In einem Satz
Resource governance control plane for heterogeneous LLM inference workloads that maximises SLO-valid goodput.

## Was sie machen
YieldOS-Lite is a Phase 1 research artifact and trace-driven simulator that investigates whether a slow-path resource-governance control plane can improve SLO-valid work over mechanistic schedulers (continuous batching, chunked prefill, prefill/decode disaggregation) when LLM inference workloads are heterogeneous. The simulator models control-plane choices including SLO urgency, KV-cache value, shape forecasts, policy cadence, and admission/dispatch decisions. Key primitives include the SLO Notary (predictive SLO governance), KV Treasury (value-aware KV cache accounting), and the Obligation Heterogeneity Index (OHI). It is not a production serving engine but a scaffold to validate governance policies before integration with real engines such as vLLM or TensorRT-LLM. The current evidence supports predictive SLO governance as the strongest validated primitive, with the largest gains observed on heterogeneous workloads such as RAG-heavy, code-heavy, batch-summary-heavy, and mixed-enterprise traffic.

## Gründer
- **nikitph** — Repository author / researcher
  - LinkedIn: —
  - E-Mail: —

## Traction
- Phase 1 MVP simulator completed with ablation experiments
- Research paper draft published in repository
- Open-source repository on GitHub (nikitph/yieldos)

## Finanzierung
—

## Bewertung (LLM)

| Dimension | Score |
|---|---|
| Thesis-Fit | 3/5 |
| Team-Qualität | 1/5 |
| Frühphasen-Vorteil | 5/5 |
| Traction | 2/5 |
| Erreichbarkeit | 1/5 |

**Begründung:** YieldOS adressiert einen technisch relevanten und wachsenden Markt (LLM-Inference-Infrastruktur / MLOps) und weist eine starke Nähe zu HTGFs AI-Infrastructure-Thesis auf – allerdings handelt es sich derzeit noch um ein reines Forschungsartefakt ohne nachgewiesene Produktreife oder B2B-SaaS-Vermarktung. Der einzige bekannte Gründer tritt lediglich unter einem GitHub-Handle auf; Standort, Hintergrund, akademische Pedigree und Unternehmensstruktur sind vollständig unbekannt, was eine seriöse Due-Diligence unmöglich macht. Bis eine Commercialisierungsstrategie, ein DACH-Bezug und eine identifizierbare Gründerperson erkennbar sind, ist ein Investment-Engagement verfrüht.

**Red Flags:**
- Gründer nur als GitHub-Handle 'nikitph' bekannt – kein Name, kein LinkedIn, keine E-Mail
- Kein HQ-Land / keine DACH-Präsenz nachweisbar
- Kein Unternehmen gegründet (incorporation_status unbekannt)
- Rein akademisches Forschungsartefakt (Phase-1-Simulator), kein Produktprototyp oder MVP
- Keine zahlenden Kunden, keine Pilotpartner, kein Enterprise-Bezug erkennbar
- Kein B2B-SaaS-Geschäftsmodell erkennbar
- Keine Funding-Signale oder Investoreninteresse
- Team-Größe und -Zusammensetzung vollständig unbekannt

## Quellen
- https://github.com/nikitph/yieldos
- https://github.com/about
- https://github.com/about-us
- https://github.com/team
- https://github.com/ueber-uns
- https://github.com/uber-uns
- https://github.com/jobs
- https://github.com/careers

---
*Generiert am 2026-05-25 · canonical_id: `c3d4fb41a713d26239c9c87a4af3ff23fb7abe0ba709a167f0bf7b9d51b5ba7d`*
