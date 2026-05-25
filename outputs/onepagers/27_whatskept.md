# WhatsKept

**Rang:** 27 / 46   **Score:** 2.35 / 5.00

| | |
|---|---|
| Website | [https://github.com/alkait/WhatsKept](https://github.com/alkait/WhatsKept) |
| Sitz | — |
| Gegründet | — |
| Stage | Pre-Launch |
| Sektor | DevTools · AI Data Pipeline / Privacy Tools |

## In einem Satz
A self-contained Go binary that decrypts iOS backups and turns WhatsApp history into a searchable, agent-queryable local SQLite workspace.

## Was sie machen
WhatsKept is an open-source data pipeline tool distributed as a single self-contained binary for macOS (Apple Silicon). It drives iOS backups over USB via idevicebackup2, decrypts WhatsApp's ChatStorage.sqlite and associated media/voice blobs from an encrypted iOS backup, and normalises everything into a local SQLite database with FTS5 full-text search. Media is processed entirely on-device: images are run through Apple's Vision framework for OCR and classification, and voice notes are transcribed locally via whisper.cpp with Metal acceleration. The resulting workspace — including extracted media, voice, and profiles folders, joined against macOS Contacts — is designed to be queried directly by an LLM coding agent (Windsurf, VS Code + Copilot, Claude Code, Cursor, etc.). WhatsKept has no built-in LLM, no cloud sync, no telemetry, and makes no outbound network calls beyond a one-time optional download of the Whisper model from HuggingFace. The project was built in a weekend using Claude Opus 4.7 with AI-generated code, with the creator owning all architecture and privacy decisions.

## Gründer
- **alkait** — Creator
  - LinkedIn: —
  - E-Mail: —
  - Hintergrund: Built WhatsKept in a weekend using Claude Opus 4.7; responsible for all architecture and privacy decisions

## Traction
- Open-source project hosted on GitHub
- Pre-built macOS arm64 GUI app and CLI binary available via GitHub Releases
- Built in a single weekend with ~$900 in AI token usage

## Finanzierung
—

## Bewertung (LLM)

| Dimension | Score |
|---|---|
| Thesis-Fit | 2/5 |
| Team-Qualität | 1/5 |
| Frühphasen-Vorteil | 5/5 |
| Traction | 1/5 |
| Erreichbarkeit | 1/5 |

**Begründung:** WhatsKept ist ein Open-Source-Wochenendprojekt eines einzelnen, anonymen Entwicklers ohne bekannten DACH-Bezug, Unternehmensgründung oder kommerzielle Absicht. Das Tool richtet sich primär an technisch versierte Einzelpersonen (Consumer-/Hobbyist-Nutzung) und weist keinen B2B-SaaS-Ansatz, keine Monetarisierungsstrategie und keine Enterprise-Traction auf. Ein Investment-Case im Sinne des HTGF Digital-Tech-Thesis ist derzeit nicht erkennbar.

**Red Flags:**
- Kein Unternehmen gegründet – rein privates Open-Source-Projekt
- Gründer vollständig anonym (nur GitHub-Handle 'alkait'), kein LinkedIn, keine E-Mail
- Kein DACH-HQ oder deutscher Bezug erkennbar
- Kein B2B-Modell oder Monetarisierungsstrategie
- Consumer-Nutzungsfall (persönliche WhatsApp-History), kein Enterprise-Winkel
- Solo-Entwickler, kein Team
- In einem Wochenende gebaut – keine Produktreife oder Roadmap erkennbar
- Keine Funding-Signale, kein kommerzieller Traction

## Quellen
- https://github.com/alkait/WhatsKept
- https://github.com/about
- https://github.com/about-us
- https://github.com/team
- https://github.com/ueber-uns
- https://github.com/uber-uns
- https://github.com/jobs
- https://github.com/careers

---
*Generiert am 2026-05-25 · canonical_id: `831718bd85b5032a8f72e9899e8d4c2d182d8aa11e91a04ac6aa9ca66e28e960`*
