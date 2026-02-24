# Robot Buddy — Agent Notes (Codex)

- Read `CLAUDE.md` first (repo conventions + common commands).
- Treat `docs/TODO.md` as the single source of implementation truth (priorities + tracking).
- Spec-driven: `specs/` is immutable reference; amend specs before diverging.
- Prefer `just` recipes from `justfile` (`just preflight`, `just test-*`, `just run-mock`, etc.).
- Hardware/deploy actions (`flash-*`, `deploy`, SSH) are **manual-only** unless explicitly requested.
- Avoid adding scoped `AGENTS.md` files unless repeated confusion in a subtree (≈3+ incidents) justifies it.
