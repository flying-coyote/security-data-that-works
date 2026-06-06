# Vendor reference index (template)

Per data-source vendor (the data sources, not the SIEMs), the official tools, docs, SDKs, and APIs you'd
need to build an MCP server against their product *yourself*. This is the public companion to the SDW
architect MCP server's two-axis vendor database: the **infra/admin** axis (run the system) and the
**analyst/data** axis (analyze its telemetry).

Fill in your own stack. Each row carries a `last-checked` date because the index rots like any link list and
wants a freshness pass on a cadence — the *security* guidance in the kit does not rot, because it's
referenced live at build time rather than frozen here.

## Columns

- **vendor / product** — the data source.
- **official MCP?** — does the vendor publish one? (yes / no / partial)
- **transport** — stdio (air-gappable) / Streamable-HTTP / cloud-hosted-managed (the air-gap dividing line).
- **self-hostable** — can you run it in your own environment?
- **air-gappable** — does it work with no outbound network?
- **build-your-own refs** — the official tools / SDK / API docs you'd build against if you build it yourself.
- **notes** — gotchas (phone-home, schema curation, auth model).

## Template

| vendor / product | official MCP? | transport | self-hostable | air-gappable | build-your-own refs (tools / SDK / API) | notes |
|---|---|---|---|---|---|---|
| _e.g._ network detection (NDR) | no | — | n/a | n/a | vendor REST/streaming API docs; export-to-lake connector | no MCP; build against the API, or ingest to your lake and self-host an MCP over your copy |
| _e.g._ EDR | partial | cloud-hosted | no | no | vendor query API + detection-content export | SaaS MCP phones home; the air-gap fallback is ingest-and-self-host |
| _e.g._ open NDR (Zeek-based) | yes | stdio | yes | yes | the open agent/sensor API + log schema | self-hostable; the legible case |
| _your source_ | | | | | | |

## The fallback rule

For any SaaS-only source with no air-gappable MCP, the fallback is the same: **ingest its telemetry into
your own lake and self-host an MCP over your copy**, so the analyst surface is local even when the source
isn't. That keeps the build-your-own posture intact regardless of how the vendor ships.

> This is a starting template, not a maintained directory. Populate it for the vendors in your environment,
> date each row, and re-check on the cadence that matches how fast those vendors change their APIs.
