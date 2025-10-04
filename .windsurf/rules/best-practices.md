---
trigger: always_on
---

When proposing changes:
- First output a 5–10 line plan + risk list.
- Show EXACT files to touch; avoid collateral edits.
- Write/modify tests FIRST (pytest). No real network calls in unit tests.
- Prefer pathlib, quoted subprocess calls, Windows-safe shells.
- Be paranoid about secrets; read from env; redact logs.
- For ingestion: never drop audio; on failure, retry with exponential backoff + jitter; classify errors (429/403 vs 4xx permanent).
- If unsure about a file path or env var name, stop and ask.
- After patch, run a “self-review”: list 5 things most likely to break and how you mitigated them.
