# Git hooks

This repo is **public**. The `pre-commit` hook blocks staged files whose names match
internal design/strategy/review patterns (`*DESIGN*.md`, `REVIEW-*.md`, `*ALIGNMENT*.md`,
`*-BRANCH.md`, `*MATURITY*.md`, `*ASSESSMENT*.md`) so consultant-internal notes stay in
`~/project1` and don't land in the public history. Public docs (`README.md`, `CONTRACT.md`,
`MOAR-EVIDENCE-RUN-*.md`) are intentionally not matched.

Activate (once per clone):

```bash
git config core.hooksPath .githooks
```

Override a false positive for a single commit with `git commit --no-verify`.
