# Agent Playbook Suite

**Rang:** 17 / 31   **Score:** 2.50 / 5.00

| | |
|---|---|
| Website | [https://artrichards.github.io/agent-playbook-suite/blog](https://artrichards.github.io/agent-playbook-suite/blog) |
| Sitz | — |
| Gegründet | — |
| Stage | Pre-Launch |
| Sektor | DevTools · AI Coding Agent Tooling |

## In einem Satz
A CLI and plugin suite that persists coding-agent project state as validated Markdown records in the repository, making multi-session AI-assisted development resumable.

## Was sie machen
Agent Playbook Suite addresses a core problem with LLM coding agents: they can write code but struggle to maintain coherent project state across multiple sessions. The solution is to write project state as small, structured Markdown records stored directly in the repository, validated by a CLI tool called docs-cli, and accessed by agents through a defined set of verbs (create, archive, move, touch, list, check, index, migrate) rather than relying on chat history or context windows. The suite is distributed as a single marketplace plugin for Codex and Claude Code, bundling the `docs` skill alongside five workflow skills: project-foundation (sets up charters, scope, architecture, milestones), create-milestones (operator-driven TDD delivery loop), ship-milestone (autonomous conductor that delegates to fresh sub-agents), sync-and-commit (step-boundary verification, doc update, diff review, and push), and simplify. The CLI (`docs-cli` on PyPI) provides the runtime substrate; the plugin provides the behavioral layer. The design was dogfooded against 25 real-world Markdown trees (501 files), achieving 88% high-or-medium confidence in migration inference and producing iterative design improvements such as using `Lifecycle:` instead of `Status:` for controlled fields.

## Gründer
- **Art Richards** — Creator
  - LinkedIn: —
  - E-Mail: —

## Traction
- Dogfooded across 25 real-world Markdown trees (501 files)
- 88% high-or-medium confidence migration inference
- Published on PyPI as docs-cli
- Plugin distributed via public marketplace (Codex, Claude Code)

## Finanzierung
—

## Bewertung (LLM)

| Dimension | Score |
|---|---|
| Thesis-Fit | 2/5 |
| Team-Qualität | 1/5 |
| Frühphasen-Vorteil | 5/5 |
| Traction | 2/5 |
| Erreichbarkeit | 1/5 |

**Begründung:** Agent Playbook Suite adressiert ein reales Problem im Bereich KI-gestützter Entwicklung (Zustandspersistenz über mehrere Sessions hinweg) und passt grundsätzlich in den DevTools-/AI-Coding-Bereich. Allerdings fehlen entscheidende HTGF-Kernkriterien: Es gibt keinerlei Hinweise auf einen DACH-Sitz, ein B2B-SaaS-Geschäftsmodell oder zahlende Enterprise-Kunden – das Projekt wirkt eher wie ein Open-Source-Einzelprojekt. Das Gründerteam ist auf einen einzigen, nicht verifizierbaren Creator reduziert, ohne nachweisbares akademisches oder Exit-Hintergrund sowie ohne jegliche Kontaktierbarkeit.

**Red Flags:**
- Kein DACH-Sitz nachweisbar – HQ-Land und -Stadt unbekannt
- Solo-Gründer ohne verifizierbares Profil (kein LinkedIn, keine E-Mail)
- Kein B2B-SaaS-Geschäftsmodell erkennbar – aktuell reines Open-Source/CLI-Tool
- Kein Gründungsjahr, keine Inkorporation, kein Funding-Signal
- Traction beschränkt sich auf Dogfooding des eigenen Projekts, keine externen Nutzer oder Kunden
- Keine Kontaktierbarkeit – weder LinkedIn noch E-Mail des Gründers vorhanden
- GitHub-Seite statt echter Unternehmenswebsite deutet auf frühe Einzelperson hin

## Quellen
- https://artrichards.github.io/agent-playbook-suite/blog
- https://artrichards.github.io/about
- https://artrichards.github.io/about-us
- https://artrichards.github.io/team
- https://artrichards.github.io/ueber-uns
- https://artrichards.github.io/uber-uns
- https://artrichards.github.io/jobs
- https://artrichards.github.io/careers

---
*Generiert am 2026-05-25 · canonical_id: `26c194c7f3911abdbf45b6aa305530944efa031e539f94687ec91727cf47def0`*
