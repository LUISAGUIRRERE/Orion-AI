# AI Board — Single Source of Truth (MISSION G-012)

## Purpose

Before this Mission, the AI Board's roster (Luis Aguirre, ChatGPT, Claude, Jules, Nemotron, AutoClaw) was written out by hand, twice, with slightly different wording each time: once in the "AI Board" table of [`AGENTS.md`](../AGENTS.md), and once in the "Membership" table of [`.ai/BOARD.md`](../.ai/BOARD.md). Nothing enforced that the two ever agreed, and nothing would have caught it if a future edit updated one and not the other.

`.ai/board.yaml` is now the single, machine-readable place that data lives. The two tables above are *generated* from it and must never be edited by hand.

## Location and schema

- **Canonical source:** [`.ai/board.yaml`](../.ai/board.yaml)
- **Format:** YAML (already a dependency of every other `orion.*` module; no new dependency was introduced)
- **Loader/validator:** `orion.board.canonical` (`load_board_config()`, raises `BoardConfigurationError` with a specific, actionable message on any problem)
- **Schema (`schema_version: 1`):**

  ```yaml
  schema_version: 1        # int, must be a version this ORION supports
  board_version: 1         # int, bumped whenever the roster changes
  members:
    - id: jules                          # unique, required
      display_name: Jules                # unique, required
      role: Lead Software Engineer       # required, non-empty
      status: active                     # active | inactive | proposed
      responsibilities: [ "..." ]        # list of strings
      restrictions: [ "..." ]            # list of strings
      capabilities: [ ]                  # list of strings, currently unused
      documentation_path: .ai/prompts/jules-engineer.md   # optional; repo-relative, no absolute paths or traversal, must exist if set
      supersedes: null                   # optional; must reference a known, different member id if set
  ```

  Validation rejects, with a specific error message: unknown top-level or per-member keys, a non-integer or boolean `schema_version`/`board_version`, a non-string `id`/`display_name`/`role`, an empty `role`, an invalid `status`, a non-list `responsibilities`/`restrictions`/`capabilities` or any non-string/empty entry inside them, an absolute or path-traversing `documentation_path`, a missing documentation file, a member superseding itself, and an unknown `supersedes` reference.

## What lives where (and why it isn't duplicated)

| Document | Contains | Generated? |
|---|---|---|
| `.ai/board.yaml` | Structured identity: id, display name, role, status, short responsibilities/restrictions, doc path | No — this **is** the source |
| `.ai/ROLES.md` | Full prose per seat: "Responsible for" / "May" / "May not" / Boundaries | No — narrative, hand-written, authoritative |
| `.ai/prompts/<member>.md` | Each AI member's actual system prompt | No — hand-written |
| `agents/<member>.md` | Detailed operating instructions for one agent (e.g. `agents/gemini.md`) | No — hand-written |
| `docs/DECISIONS.md` | ADRs recording *why* the Board looks like this | No — historical record, never regenerated |
| `AGENTS.md` — "AI Board" table | Same facts as `board.yaml`, formatted for the repo's agent entry point | **Yes**, between `<!-- BEGIN GENERATED -->` / `<!-- END GENERATED -->` markers |
| `.ai/BOARD.md` — "Membership" table | Same facts as `board.yaml`, formatted for the Board's own overview doc | **Yes**, same marker convention |

Nothing outside those two marked blocks is touched by generation — headings, "Purpose," "Operating Model," and every other paragraph in both files remain hand-written.

## Adding or Updating an AI Board Member

1. **The membership decision must already exist.** Adding, removing, or changing a Board seat is a real governance decision, not a data-entry task — it needs an ADR in `docs/DECISIONS.md` (see ADR-0001, ADR-0006) approved the same way any Architecture/Governance change is, per `.ai/DECISION_PROCESS.md`. `.ai/board.yaml` records a decision that has already been made; it does not make the decision.
2. Once approved, edit **only** `.ai/board.yaml` for the structured facts (id, display_name, role, status, responsibilities, restrictions, documentation_path).
3. If the member needs full narrative boundaries, add or update the corresponding section in `.ai/ROLES.md` by hand (never generated).
4. If the member needs a system prompt or detailed agent instructions, add or update `.ai/prompts/<member>.md` and/or `agents/<member>.md` by hand.
5. Run `orion board validate` to confirm the new YAML is well-formed and every reference (documentation paths, `supersedes`) resolves.
6. Run `orion board generate` to sync `AGENTS.md` and `.ai/BOARD.md`'s generated tables. Commit the diff.
7. Never hand-edit anything between the `BEGIN GENERATED`/`END GENERATED` markers — the next `orion board generate` run will silently overwrite it.

**Important:** creating `agents/<member>.md` (or any other narrative doc) does **not**, by itself, make someone an official Board member. Only an entry in `.ai/board.yaml`, backed by an approved ADR, does. `agents/gemini.md` exists today; Gemini is deliberately **not** listed in `.ai/board.yaml`, because no ADR has added it as a seat (see ADR-0006).

## CLI

- `orion board validate` — loads and validates `.ai/board.yaml`; never writes anything; prints every problem found or the resolved roster.
- `orion board generate` — regenerates `AGENTS.md`/`.ai/BOARD.md`'s tables; writes only the files that actually changed; idempotent (running it twice with no `board.yaml` change produces zero further changes).
- `orion board generate --check` — same validation and comparison as `generate`, but never writes; exits non-zero if any target has drifted from what `.ai/board.yaml` would produce. Intended for CI.

## API

- `GET /api/board/roster` — the real AI Board roster (id, display_name, role, status, responsibilities, restrictions, documentation_path). Never returns the contents of any prompt/agent file, only its path.
- `GET /api/board/members` — unchanged from B-011 (Mission pipeline stages); its `board_seat` label is resolved fresh, per request, directly from `.ai/board.yaml` (never cached, never a hardcoded fallback string); if resolution fails, `board_seat` is `null` and the real reason is available via `orion board validate`, with no change to the response shape.

## Compatibility

- `orion.board.member_registry`'s public API (`MEMBERS`, `ALL_KEYS`, `get_member()`, `list_members()`) is unchanged. `MEMBERS` holds the static pipeline-stage templates only (never a resolved seat). `get_member()`/`list_members()` resolve `board_seat` fresh against `.ai/board.yaml` on every call — no caching, no fallback identity. If the canonical file cannot be loaded, `board_seat` is `None` and `board_seat_error` holds the real error message, so a broken YAML never crashes Governance, Runtime, the CLI, the API, or the Window — it only means the seat label is reported as unavailable, with the real reason attached.
- B-011's Mission pipeline selection (`orion.board.board_engine.decide_pipeline`) is entirely unaffected — it never reads `.ai/board.yaml` at all.
- Every existing `/api/board/*` route continues to work exactly as before; `/roster` is additive.

## Write safety (what "atomic" actually means here)

`orion board generate` writes two target files (`AGENTS.md` and `.ai/BOARD.md`). It is important to be precise about what is and is not guaranteed, since "atomic" is easy to overclaim:

- **Per-file atomicity — real, filesystem-backed.** Each target is written to a temp file in its own directory and swapped into place with `os.replace()`, which is atomic on the same filesystem. A reader can only ever see that one file's old, complete content or its new, complete content — never a truncated or partially-written file.
- **Set-level coherence across the two targets — compensating rollback, not a filesystem transaction.** Ordinary filesystems do not offer a transaction spanning two independent files, and this module does not pretend otherwise. Instead: every target is rendered and validated *before* anything is mutated; every target's original content is backed up and every target's replacement temp file is fully prepared *before* any real path is touched; only then are the per-file atomic swaps performed, in order. If a later swap fails, every target already swapped in that same run is restored — via another per-file atomic write — back to its backed-up original content, so a caller never observes one file updated to the new roster and the other still on the old one; a `GeneratorError` is raised either way, naming what failed.
- **A subsequent `generate()` always self-heals.** Since generation is idempotent and re-reads `.ai/board.yaml` fresh every time, running `orion board generate` again after any failure (rolled back or not) reconciles both targets correctly.
- **Disclosed limit.** The restore step is itself a real write and can theoretically fail too (e.g. the filesystem that just rejected a replace becomes fully unwritable). In that case `GeneratorError`'s message names every target it could not restore, and manual inspection is genuinely required — this is not silently reported as success. Similarly, if the process is killed at the exact instant between one target's swap and the next (or during the restore itself), the two targets can transiently disagree; there is no protection against that specific abrupt-termination window beyond re-running `orion board generate --check` (or `generate`) afterward, which will detect and fix any remaining drift, since generation always compares against the current `.ai/board.yaml`, never against in-memory state left over from the interrupted run.

## Detecting drift (CI)

Run `orion board generate --check` in CI. A non-zero exit means `AGENTS.md` or `.ai/BOARD.md` no longer matches what `.ai/board.yaml` would produce — usually because one was hand-edited. Fix by running `orion board generate` (without `--check`) and committing the result, never by hand-editing the generated block.

## Rollback

If this Mission's change needs to be reverted:

1. Revert the merge commit(s) introduced by branch `feat/ai-board-single-source-of-truth` (or the specific commits: see this Mission's final report for exact hashes).
2. That restores `AGENTS.md` and `.ai/BOARD.md` to their previous, fully hand-written state, restores `orion/board/member_registry.py`'s original always-resolved (no `board_seat_error` field) shape, and removes `.ai/board.yaml`, `orion/board/canonical.py`, and `orion/board/generator.py`.
3. No agent file under `agents/` or `.ai/prompts/` is deleted by this Mission or by reverting it — none of them are touched.
4. No import outside `orion.board` depends on `orion.board.canonical` or `orion.board.generator`, so reverting cannot break any other module.
5. Verify with: `python3 -m unittest discover -s tests` (expect the same test count as before this Mission, since `tests/test_board_canonical.py` is removed along with the revert).
