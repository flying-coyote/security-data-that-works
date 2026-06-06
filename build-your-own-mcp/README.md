# Build your own MCP, don't adopt a black box

The argument is simple: for a security-data MCP server, building one yourself in your own environment from a
curated set of references beats adopting a vendor's pre-built, potentially-vulnerable, phone-home server. Not
because vendor MCPs are bad, but because a hand-me-down MCP can be quietly unsafe and you can't tell without
reading its internals, and the things that make it unsafe are exactly the things your own network controls
can't see.

## The cautionary example is first-party

While building a vendor-evaluation MCP server, the code executor in it ran user-supplied code through an
in-process `exec()` and enforced neither a memory limit nor a timeout. A single request asking it to allocate
without bound would hang or OOM the host. Egress filtering doesn't stop that, network segmentation doesn't
stop that, a sandbox at the perimeter doesn't stop that — it's an in-process denial-of-service that lives
inside the tool, and you only find it by reading the code. That is the class of risk that a downloaded
black-box MCP hides and a locally-built one lets you control.

## The spine: living references + local build + your own controls

This kit is deliberately **not** a frozen hardening checklist that SDW maintains and you download, because
that recreates the staleness problem and is the heavier, wrong model. The spine is:

1. **Living references, fetched current at build time.** SDW curates the *index of what to consult*, not the
   content. The builder pulls the current best guidance from the referenced sources at build time, so safety
   tracks the latest evidence rather than someone's last snapshot.
2. **A local build, in your own environment.** A locally-built, locally-run MCP is not
   built-elsewhere-and-downloaded, so the supply-chain, black-box, and phone-home risks largely evaporate,
   and the deployment is immediately wrapped in your own controls (egress filtering, segmentation, sandbox,
   least-privilege). That is defense-in-depth that does not depend on the generated code being perfectly
   hardened.
3. **The one residual the controls miss, handled by reference.** The in-process class above (a
   code-execution or query surface that can hang or OOM the host regardless of network controls) is the part
   network controls can't reach, so the curated references below specifically cover input validation and
   resource/timeout limits on any execution surface. That resolves to "point to the right references," not
   to a maintained spec.

## What's in the kit

- **[`vendor-reference-index.md`](vendor-reference-index.md)** — a template. Per data-source vendor (the data
  sources, not the SIEMs), the official tools, docs, SDKs, and APIs you'd need to build an MCP against their
  product yourself. The public companion to the architect MCP server's two-axis (infra-admin / analyst-data)
  vendor database. Fill it in for your stack; the index rots like any link list, so it carries a
  last-checked date per row and wants a freshness pass on a cadence — the *safety* guidance below does not
  rot, because it's referenced live rather than frozen.

- **The single-line build prompt** (below) — run it in your own (air-gappable) environment over the gathered
  references. It points to the references and applies their *current* guidance at build time; it does not
  hard-code a checklist that ages.

- **Curated security references** (below) — cite-and-extend, not re-authored. The generic MCP-security
  advice belongs to the projects that own it; SDW's contribution is the security-data synthesis and the
  air-gap / build-your-own framing, plus curating the set so it covers the in-process safety class your
  network controls miss.

## The single-line build prompt

Run in your own environment, with the referenced docs gathered under `./refs/`:

> "Build a read-only MCP server exposing `<product>`'s `<capabilities>` over stdio, following the current
> security and design guidance in the references under `./refs/` (the Anthropic MCP security documentation,
> the OWASP MCP Top 10, and the linked best-practices repos): validate every tool input against a schema;
> enforce a hard memory cap and a wall-clock timeout on any code-execution or query surface; default-deny
> egress; emit no telemetry off-host; and cite, in a comment on each control, which reference it came from."

The prompt names the references rather than the rules, so when the guidance updates, the next build picks up
the update without anyone editing this repo.

## Curated security references (cite and extend)

- **[claude-code-project-best-practices](https://github.com/flying-coyote/claude-code-project-best-practices)**
  — the evidence-tiered audit method this kit's posture comes from (curate the index of what to consult; let
  the consumer fetch current evidence at use time).
- **Anthropic's official MCP documentation and security guidance** — the protocol, the transports (stdio vs
  Streamable-HTTP, the latter being the air-gap dividing line), and the current security guidance. Consult
  the live docs at build time rather than a copy here.
- **The OWASP MCP Top 10** — the risk taxonomy (tool poisoning, the confused-deputy pattern, rug-pull
  updates). Curated into the kit specifically because it names the in-process and supply-chain classes that
  egress rules don't catch.
- **The MCP server's own internals** — if you do adopt a vendor MCP, read its execution surface: how it runs
  any user-supplied or model-supplied code, and whether it bounds memory and time. The `exec()`-without-limits
  example above is what you're looking for.

## How this connects

This kit is the operational form of three positions: the air-gap ask turned from a vendor request into a
buyer capability; sub-frontier local inference building from a grounded bundle; and contribute-don't-own
(a spec and a curated index are not a competing tool, so the generic MCP-security advice is cited rather than
forked). The spec it belongs to is in [`../SPEC.md`](../SPEC.md).

## Read alongside (securitydataworks.com)

- [MCP for data engineering](https://securitydataworks.com/writing/ai/mcp-for-data-engineering) — the case this kit operationalizes
- [the MCP-server landscape (research)](https://securitydataworks.com/research) — the scored inventory of security-data MCP servers (self-hostable / air-gappable / legibility), the evidence behind "build your own"
- [Defining what you can own](https://securitydataworks.com/writing/ai/defining-what-you-can-own) — the air-gap-ask-as-buyer-capability position
- back to the [repo front door](../README.md) and the open [SPEC.md](../SPEC.md)
