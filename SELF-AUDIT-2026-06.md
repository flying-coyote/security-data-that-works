---
repo: security-data-that-works
date: 2026-06-21
source: WF-C intent self-audit
method: intent-alignment question bank (analysis/intent-alignment-audit.md) over the 16 Fable prompts
status: complete
---

# Intent self-audit — security-data-that-works (2026-06-21)

This is the "why" pass, not a presence checklist. For each load-bearing mechanism I asked
whether it still matches the reason it was added, following the portable intent question bank
(`~/claude-code-project-best-practices/analysis/intent-alignment-audit.md`, evidence-tier B).
Citations are real file:line read on 2026-06-21. I did not run git and touched no other files.

## What this repo is FOR (Q1 — goal)

One sentence: it is the **public front door** to Security Data Works — a runnable, evidence-first
statement of "what good looks like" for security data, whose flagship demo is a deductive OCSF→D3FEND
field-mapping gate that catches the wrong mapping that silently kills a detection, with the per-vendor
*scoring* deliberately held back as paid IP.

The goal is stated consistently and well across the surfaces that should hold it:
- `README.md:3-6` — "a small, runnable demo of one idea."
- `SPEC.md:1-7` — "states *what good looks like* … as a method rather than a product," with the public-method / paid-score line drawn explicitly.
- `CONTRIBUTING.md:1-3` — "a front door to the open projects it stands on, not a fork of them."

This is a genuinely healthy Q1: three surfaces, one goal, no fragmentation. The public/paid boundary
(the thing most likely to be muddled in a repo like this) is restated in all three and is enforced in
code, not just prose (`paid_scoring.py:1-12` — scores load only under `MOAR_PAID_MODE` and a pre-flight
assertion refuses to read them from anywhere inside the public repo). The intent is documented and the
boundary is mechanically promoted, which is exactly the Q8 (decisions→policy) graduation the bank wants.

## Does the current structure still serve that? (Q2 — self-model)

Mostly yes, but the repo has outgrown its own framing in one direction. The README presents four roughly
co-equal demos (`gate/`, `docker/`, `foundation-healthcheck/`, `build-your-own-mcp/`), and that was an
accurate self-model when written. The live tree is now lopsided: `docker/` is the overwhelming bulk of
the repo — a 538-line `moar` orchestrator (`docker/moar`) with ~24 subcommands, a 305-line README, a
~32KB second README, a `control-plane/` of **35 application modules + 31 `prove_*` harnesses**
(`docker/control-plane/`), bench-run artifacts, a marimo console, and a generated flip-through PDF. The
other three "demos" are comparatively tiny: `gate/` is one validator + two CSVs + expected output,
`foundation-healthcheck/` is a single notebook + its `.py`, `build-your-own-mcp/` is two markdown files.

So the self-model that reads as "four demos of equal weight" understates how much of the repo is now the
MOAR docker/console stack. That is not wrong, but it is the early form of intent-mechanism drift: the
README's framing was set when the gate was the flagship and the docker stack was one of four siblings; the
center of gravity has moved to the console and the framing hasn't caught up. **Verify and decide**: is the
public front door still "the gate, plus three companions," or is it now "the MOAR console, with the gate as
its data-health entry point"? The repo would read more honestly if it picked one.

## Where it is most likely WRONG (Q5)

Two candidates, in priority order.

1. **The disjointness adjudication at scale — and the repo says so itself.** `README.md:104-115` ("Honest
   limits") is unusually candid: the eight-artifact hand-authored disjointness layer is Tier B, validated on
   *injected* type-crossings (231/231 on the 925-row corpus, 22/22 on an 83-field holdout), not on a held-out
   set of confirmed human errors, and the false-positive risk rises as the artifact set widens because
   genuinely-overlapping pairs (a credential *can* be stored in a file) start to appear. This is the
   load-bearing claim and the repo has already written its own falsifier. The intent-bank promotion here is to
   turn that prose caveat into a tracked Gap with a named test — e.g. score the layer against a real corpus of
   *confirmed* human mapping errors, not injected ones — so "where am I most wrong" stops being a paragraph and
   becomes a falsifiable item.

2. **The "front door to open projects, not a fork" framing vs. the private-vault couplings in the code.**
   Several public `control-plane` modules reference a private filesystem and an uncommitted internal design
   doc by name (see the dead-weight / boundary finding below). The repo *claims* to be a clone-and-run front
   door; parts of the console silently assume `~/project1` exists. For the `gate/` flagship the claim holds
   (`./gate/run.sh` is genuinely self-contained, Docker-wrapped). For the console it is weaker than the README
   implies. The belief most likely wrong is "any clone gets the same experience" — true for the gate, partly
   false for the console.

## Dead weight / what should be archived or killed

The repo is young (first commits within the last ~30 days; 113 commits in 90 days, all by one author) and
mostly lean — there is little classic stale cruft. The items worth attention are couplings, not corpses:

- **Dangling internal-doc reference in public files.** `MOAR-CONTROL-PLANE-EXTENSION-DESIGN.md` is referenced
  by name in `docker/control-plane/CONTRACT.md:16` and `docker/control-plane/paid_scoring.py:12`, but the doc
  itself is **not committed** (it lives in project1). A reader of the public repo is pointed at a file they
  cannot open. This is precisely the class the pre-commit hook was added on 2026-06-20 to stop
  (`.githooks/pre-commit:6-7` — four internal docs had to be scrubbed from history after the fact). The hook
  blocks internal *files* by name; it does not catch internal *references* inside public files. Either commit a
  public-safe version of that design note, or replace the by-name pointers with a self-contained explanation
  (CONTRACT.md:9-17 already gives most of it — the pointer is now redundant).
- **`~/project1` hardcoded as a default in public code.** `control_plane.py:50-51,1125,1161,1187` and
  `paid_scoring.py:6,18,65` default `VAULT_PATH` to `~/project1` and render UI copy that names "the project1
  strategy vault." For an external cloner that path does not exist; the panel degrades to "Vault unreadable."
  Functionally it fails gracefully, but it leaks the maintainer's private layout into the public surface and
  reads as a half-finished feature to anyone who isn't Jeremy. Consider gating the whole OKF-vault panel behind
  the same `MOAR_PAID_MODE` flag that already gates scoring, so the public clone never sees a vault path it
  can't satisfy.
- **Two `MOAR-EVIDENCE-RUN-*.md` snapshots** (2026-06-15, 2026-06-20) are intentionally public per the hook's
  allow-list and are fine as dated evidence; not dead weight, just noting they will accumulate — a date-stamped
  evidence log wants a retention rule before it becomes a dozen near-identical files.

Nothing here rises to "archive a whole directory." The repo has not yet accreted the stale-glob / outdated-count
problems the intent doc was written against; its risk is the opposite — fast growth outrunning its own framing.

## Bus factor (Q9)

Single author across all 113 commits (`git log --format=%an` → 113 × flyingcoyote). The fragile
one-person dependency is the **disjointness adjudication itself**: the judgment that "executed-from" and
"stored-in" are *relations* not *identity*, and therefore which of the eight D3FEND artifact pairs are
soundly disjoint, is hand-authored expert knowledge (`README.md:91-97`, `CONTRIBUTING.md` D3FEND section).
The `--selfcheck` mode proves the layer is internally *consistent*, but it cannot prove the adjudication is
*correct* — that rests entirely on the author's ontology judgment. If Jeremy stepped away, someone could run
the gate but could not safely extend the artifact set without reproducing that judgment, and the false-positive
risk the README flags is exactly what an unguided extension would trip. The promotion path is the one
CONTRIBUTING already points at: push the disjointness extensions upstream into D3FEND (#423) where the
adjudication gets community review, rather than keeping the expert call private to this repo.

## Loops / scheduled jobs / automation, and the RETHINK instrument (Q3/Q4)

**Does it run loops or scheduled jobs? No** — and this is a deliberate, documented design choice rather than
an absence. There is no cron, no `/loop`, no `.github/workflows` scheduled agent, no Desktop scheduled task,
no `while true` daemon. The `while True` hits in `layer3_audit.py:105` and `lab/workload_matrix.py:74` are
bounded iteration loops inside synchronous analysis functions, not unattended schedulers. `prove_evidence.py:37`
has a `sleep 5` in a test stub. The `moar` orchestrator is verb-driven (`up`/`verify`/`swap-*`/`bench`/…),
invoked by a human, not scheduled.

Crucially, the repo **already contains the RETHINK instrument the intent doc says a looping system needs — and
chose freshness-decay over a loop precisely so it wouldn't have a strong-Act/stale-Orient gap.** `decay.py:1-8`
is explicit: "marimo is a reactive notebook, not a daemon, so this is the honest substitute for a built-in
cron: the verdict ages and a manual re-run refreshes it; an external scheduler is documented, not faked." A
measured `pass` rots to `stale` past a one-day TTL (`DEFAULT_TTL_SECONDS = 86400`), and the gate treats `stale`
as not-green-but-not-failed ("re-run me," not "broken"). The fail-closed contract even downgrades an *undatable*
or future-stamped pass to `stale` (`decay.py:10-15`). This is the Orient step done right for a non-looping
system: instead of acting unattended on a stale verdict, the system refuses to present an old GREEN as current
and forces a human re-derive. The CONTRACT's `stale`/`unmeasured`/`unwired` vocabulary
(`control-plane/CONTRACT.md:21-30`) is the same discipline — it distinguishes "machinery ran and passed,"
"machinery exists but had nothing to run," and "no machinery at all," so a clean-but-unexercised foundation
reads AMBER by design rather than falsely green.

So on the loop/RETHINK axis this repo is a **positive case**, not a finding. The one thing it lacks is the
*goal-level* re-check (is the front-door framing still right as the repo grows — the Q2 self-model drift above);
the *evidence-level* re-check (is this GREEN still true) is genuinely well-built.

## Where it is genuinely fine (don't manufacture problems)

- The gate flagship is honest and self-contained: model-free verdict, Docker-wrapped, with a `--selfcheck`,
  captured expected output (`gate/expected/`), and a written falsifier in the README.
- The public/paid boundary is enforced in code, not just asserted (`paid_scoring.py`), and the pre-commit hook
  (`.githooks/pre-commit`) is a real, recently-added guard against the exact leakage that bit the repo on
  2026-06-20.
- 31 `prove_*` harnesses against 35 modules is a strong inner-loop self-verification ratio for a console of this
  size — "is it better" is mechanically checkable here, which is more than most repos this young have.

## Top recommendations (priority order)

1. **Resolve the dangling `MOAR-CONTROL-PLANE-EXTENSION-DESIGN.md` reference** in `CONTRACT.md:16` and
   `paid_scoring.py:12` — commit a public-safe version or inline the needed content; the hook guards file names,
   not in-file references.
2. **Gate the `~/project1` OKF-vault couplings** (`control_plane.py:50-51,1125-1187`, `paid_scoring.py`) behind
   `MOAR_PAID_MODE` so a public clone never renders a private vault path.
3. **Reconcile the README self-model** — decide whether the front door is still "the gate + three companions" or
   "the MOAR console with the gate as its data-health door," and frame to match the current weight.
4. **Promote the README "Honest limits" caveat to a tracked Gap** with a named test (score the disjointness layer
   against confirmed human errors, not injected ones), and push artifact-set extensions upstream to D3FEND #423
   to reduce the one-person adjudication bus-factor.
