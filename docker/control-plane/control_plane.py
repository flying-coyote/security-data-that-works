import marimo

__generated_with = "0.23.10"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _():
    import marimo as mo
    import os
    import subprocess
    import textwrap
    import yaml

    try:
        from pyiceberg.catalog.rest import RestCatalog
    except ImportError:
        RestCatalog = None

    import sys
    sys.path.append(os.path.abspath("."))
    import pulumi_deployer as deployer
    import providers as P
    import okf_reader as okf
    import ui_helpers as ui
    import gate_logic as gl
    import layer3_audit as l3
    import layer1_audit as l1
    import layer4_audit as l4
    import decay as dk
    import evidence_runner as ev

    # Tolaria convention: point VAULT_PATH at the OKF vault (project1).
    VAULT_PATH = os.environ.get("VAULT_PATH", os.path.expanduser("~/project1"))
    return P, RestCatalog, VAULT_PATH, deployer, dk, ev, gl, l1, l3, l4, mo, okf, os, subprocess, textwrap, ui, yaml


@app.cell(hide_code=True)
def _(mo):
    branding_styles = mo.Html("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&family=JetBrains+Mono:ital,wght@0,100..800;1,100..800&family=Noto+Color+Emoji&display=swap');

    :root {
      --color-teal-400: #5c8dc5;
      --color-teal-500: #4577b0;
      --color-teal-600: #36608f;
      --color-orange-500: #8c7e6e;

      --color-bg-primary: #ffffff;
      --color-bg-subtle: #f4f6f8;
      --color-border-subtle: #e2e6ea;
      --color-text-muted: #67768a;
      --color-text-primary: #1f2933;
      --color-text-display: #0c1620;

      --font-sans: "DM Sans", system-ui, sans-serif;
      --font-mono: "JetBrains Mono", monospace;
    }

    @media (prefers-color-scheme: dark) {
      :root {
        --color-bg-primary: #0c1620;
        --color-bg-subtle: #15212e;
        --color-border-subtle: #233344;
        --color-text-muted: #909eae;
        --color-text-primary: #e2e6ea;
        --color-text-display: #f4f6f8;
        --color-teal-500: #87aacf;
      }
    }

    .marimo-app {
      background-color: var(--color-bg-primary) !important;
      color: var(--color-text-primary) !important;
      font-family: var(--font-sans), "Noto Color Emoji", sans-serif !important;
    }

    h1, h2, h3, h4, h5, h6 {
      color: var(--color-text-display) !important;
      font-family: var(--font-sans), "Noto Color Emoji", sans-serif !important;
      font-weight: 600 !important;
      letter-spacing: -0.025em !important;
      margin-top: 1.5rem !important;
      margin-bottom: 0.5rem !important;
    }

    code, pre {
      font-family: var(--font-mono) !important;
      background-color: var(--color-bg-subtle) !important;
      border: 1px solid var(--color-border-subtle) !important;
      color: var(--color-text-primary) !important;
    }

    /* One consistent size for every card/section header so the selection
       pane stops mixing markdown heading levels. */
    .sdw-card-h {
      font-family: var(--font-sans), "Noto Color Emoji", sans-serif;
      font-size: 0.95rem;
      font-weight: 600;
      letter-spacing: -0.01em;
      color: var(--color-text-display);
      margin-bottom: 0.6rem;
    }

    button.marimo-button, .marimo-button button, [role="tab"] {
      font-family: var(--font-sans), "Noto Color Emoji", sans-serif !important;
      font-weight: 500 !important;
      border-radius: 0px !important;
      border: 1px solid var(--color-border-subtle) !important;
      background-color: var(--color-bg-subtle) !important;
      color: var(--color-text-primary) !important;
      transition: all 150ms ease !important;
      padding: 0.5rem 1rem !important;
    }

    button.marimo-button:hover, .marimo-button button:hover, [role="tab"]:hover {
      border-color: var(--color-teal-400) !important;
      color: var(--color-teal-600) !important;
    }

    .sdw-header {
      display: flex;
      align-items: center;
      gap: 1rem;
      border-bottom: 2px solid var(--color-border-subtle);
      padding-bottom: 1rem;
      margin-bottom: 2rem;
    }

    .sdw-title {
      font-size: 1.8rem;
      font-weight: 700;
      letter-spacing: -0.03em;
      color: var(--color-text-display);
    }

    .sdw-title span.works { color: var(--color-teal-400); }
    </style>
    """)
    header_lockup = mo.Html("""
    <div class="sdw-header">
    <svg width="40" height="40" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="5" y="5" width="26" height="26" fill="#c14a4a" />
        <rect x="37" y="5" width="26" height="26" fill="#d6824a" />
        <rect x="69" y="5" width="26" height="26" fill="#d6b94a" />
        <rect x="5" y="37" width="26" height="26" fill="#d6b94a" />
        <rect x="37" y="37" width="26" height="26" fill="#6f9a4f" />
        <rect x="69" y="37" width="26" height="26" fill="#36608f" />
        <rect x="5" y="69" width="26" height="26" fill="#6f9a4f" />
        <rect x="37" y="69" width="26" height="26" fill="#36608f" />
        <rect x="69" y="69" width="26" height="26" fill="#5c8dc5" />
    </svg>
    <div class="sdw-title">Security Data <span class="works">Works</span></div>
    </div>
    """)
    return branding_styles, header_lockup


@app.cell(hide_code=True)
def _(branding_styles, header_lockup, mo):
    mo.vstack([
        branding_styles,
        header_lockup,
        mo.md("""
        ### MOAr Stack Control Plane
        Reactive administrator cockpit for the Modular Open Architecture (MOAr) Stack.
        """),
    ])
    return


@app.cell(hide_code=True)
def _(os, yaml):
    config_path = "moar-spec.yaml"
    if os.path.exists(config_path):
        with open(config_path, "r") as _f:
            config_data = yaml.safe_load(_f) or {}
    else:
        config_data = {}
    return config_data, config_path


@app.cell(hide_code=True)
def _(P, config_data, mo):
    # The spec file stores the ingest category under the "pipeline" section.
    _section = {"ingest": "pipeline"}

    def _saved(category):
        return config_data.get("components", {}).get(_section.get(category, category), {})

    def _saved_single(category, key="provider"):
        code = _saved(category).get(key, P.DEFAULTS[category])
        label = P.label_for(P.CATEGORIES[category], code)
        return label if label in P.labels(P.CATEGORIES[category]) else P.default_label(category)

    def _saved_multi(category, key="provider"):
        codes = _saved(category).get(key, P.DEFAULTS[category])
        if isinstance(codes, str):
            codes = [codes]
        return {P.label_for(P.CATEGORIES[category], c) for c in codes}

    def _radio(category, key="provider"):
        return mo.ui.radio(options=P.labels(P.CATEGORIES[category]),
                           value=_saved_single(category, key), label="", inline=False)

    def _checks(category):
        saved = _saved_multi(category)
        return mo.ui.dictionary({
            p.label: mo.ui.checkbox(value=p.label in saved, label=p.label)
            for p in P.CATEGORIES[category]
        })

    storage_provider = _radio("storage")
    catalog_provider = _radio("catalog")
    schema_provider = _radio("schema", key="standard")
    pipeline_provider = _checks("ingest")
    query_provider = _checks("query")
    return catalog_provider, pipeline_provider, query_provider, schema_provider, storage_provider


@app.cell(hide_code=True)
def _(P, catalog_provider, pipeline_provider, query_provider, schema_provider, storage_provider):
    # Selected codes — derived once, consumed everywhere (no label/code drift).
    sel_storage = P.code_for(P.STORAGE, storage_provider.value) or P.DEFAULTS["storage"]
    sel_catalog = P.code_for(P.CATALOG, catalog_provider.value) or P.DEFAULTS["catalog"]
    sel_schema = P.code_for(P.SCHEMA, schema_provider.value) or P.DEFAULTS["schema"]
    sel_ingest = [P.code_for(P.INGEST, lbl) for lbl, on in pipeline_provider.value.items() if on]
    sel_query = [P.code_for(P.QUERY, lbl) for lbl, on in query_provider.value.items() if on]
    return sel_catalog, sel_ingest, sel_query, sel_schema, sel_storage


@app.cell(hide_code=True)
def _(catalog_provider, mo, pipeline_provider, query_provider, schema_provider, storage_provider, ui):
    storage_card = ui.card(mo, ui.header(mo, "Storage"), storage_provider)
    catalog_card = ui.card(mo, ui.header(mo, "Catalog"), catalog_provider)
    ingest_card = ui.card(mo, ui.header(mo, "Ingest"), *list(pipeline_provider.values()))
    query_card = ui.card(mo, ui.header(mo, "Query Engine(s)"), *list(query_provider.values()))
    schema_card = ui.card(mo, ui.header(mo, "Schema Standard"), schema_provider)

    selector_panel = ui.panel(mo,
        mo.md("### Modular Component Selection"),
        mo.md("Choose the components for your active MOAr stack deployment."),
        mo.hstack([storage_card, catalog_card, ingest_card, query_card, schema_card],
                  gap=2, justify="start", align="start"),
    )
    return (selector_panel,)


@app.cell(hide_code=True)
def _(P, mo, sel_catalog, sel_ingest, sel_query, sel_schema, sel_storage, ui):
    _notes = P.compat_notes(sel_storage, sel_catalog, sel_query, sel_ingest, sel_schema)
    if _notes:
        warnings_panel = ui.panel(mo,
            ui.header(mo, "Compatibility & Operational Notes"),
            *[ui.note(mo, level, title, body) for level, title, body in _notes],
            **{"border": "1px solid var(--color-orange-500)"},
        )
    else:
        warnings_panel = mo.md("")
    return (warnings_panel,)


@app.cell(hide_code=True)
def _(P, config_data, mo, sel_catalog, sel_storage):
    def _pipe(key, default):
        return config_data.get("components", {}).get("pipeline", {}).get(key, default)

    _store = config_data.get("components", {}).get("storage", {})
    _cat = config_data.get("components", {}).get("catalog", {})

    _default_store_port = 8333 if sel_storage == "seaweedfs" else 9000
    storage_port = mo.ui.text(value=str(_store.get("port", _default_store_port)),
                              label=f"{P.label_for(P.STORAGE, sel_storage)} Port")
    storage_bucket = mo.ui.text(value=_store.get("bucket_name", "moar-warehouse"), label="S3 Bucket Name")

    _default_cat_port = 8181 if sel_catalog == "polaris" else 19120
    catalog_port = mo.ui.text(value=str(_cat.get("port", _default_cat_port)),
                              label=f"{P.label_for(P.CATALOG, sel_catalog)} Port")

    vector_ingest_port = mo.ui.text(value=str(_pipe("ingest_port", 514)), label="Vector Ingest Port (Syslog TCP)")
    vector_observe_port = mo.ui.text(value=str(_pipe("observe_port", 8686)), label="Vector Observability Port")
    vector_metrics_port = mo.ui.text(value=str(_pipe("metrics_port", 9598)), label="Vector Prometheus Metrics Port")
    vrl_transform = mo.ui.text_area(value=_pipe("vrl_transform", ""), label="Vector VRL Transform Rule", rows=12)

    fluentbit_ingest_port = mo.ui.text(value=str(_pipe("fluentbit_ingest_port", 24224)), label="Fluent Bit Ingest Port")
    fluentbit_observe_port = mo.ui.text(value=str(_pipe("fluentbit_observe_port", 2020)), label="Fluent Bit Monitor Port")
    fluentbit_transform = mo.ui.text_area(value=_pipe("fluentbit_transform", ""), label="Fluent Bit Parsers Rule", rows=12)
    return (
        catalog_port,
        fluentbit_ingest_port,
        fluentbit_observe_port,
        fluentbit_transform,
        storage_bucket,
        storage_port,
        vector_ingest_port,
        vector_metrics_port,
        vector_observe_port,
        vrl_transform,
    )


@app.cell(hide_code=True)
def _(
    P,
    catalog_port,
    fluentbit_ingest_port,
    fluentbit_observe_port,
    fluentbit_transform,
    mo,
    sel_catalog,
    sel_ingest,
    sel_storage,
    storage_bucket,
    storage_port,
    ui,
    vector_ingest_port,
    vector_metrics_port,
    vector_observe_port,
    vrl_transform,
):
    storage_settings = ui.panel(mo,
        mo.md(f"### {P.label_for(P.STORAGE, sel_storage)} Settings"),
        mo.hstack([storage_port, storage_bucket]),
    )
    catalog_settings = ui.panel(mo,
        mo.md(f"### {P.label_for(P.CATALOG, sel_catalog)} Settings"),
        catalog_port,
    )

    pipeline_settings = []
    if "vector" in sel_ingest:
        pipeline_settings.append(ui.panel(mo,
            mo.md("### Vector Settings"),
            mo.hstack([vector_ingest_port, vector_observe_port, vector_metrics_port]),
            vrl_transform,
        ))
    if "fluentbit" in sel_ingest:
        pipeline_settings.append(ui.panel(mo,
            mo.md("### Fluent Bit Settings"),
            mo.hstack([fluentbit_ingest_port, fluentbit_observe_port]),
            fluentbit_transform,
        ))

    config_panel = mo.vstack([
        storage_settings,
        catalog_settings,
        mo.vstack(pipeline_settings) if pipeline_settings
        else mo.md("*Select at least one Ingest engine to configure.*"),
    ])
    return (config_panel,)


@app.cell(hide_code=True)
def _(mo):
    save_btn = mo.ui.run_button(label="Save Configuration Spec", kind="success")
    return (save_btn,)


@app.cell(hide_code=True)
def _(
    catalog_port,
    config_path,
    fluentbit_ingest_port,
    fluentbit_observe_port,
    fluentbit_transform,
    mo,
    save_btn,
    sel_catalog,
    sel_ingest,
    sel_query,
    sel_schema,
    sel_storage,
    storage_bucket,
    storage_port,
    vector_ingest_port,
    vector_metrics_port,
    vector_observe_port,
    vrl_transform,
    yaml,
):
    save_status = mo.md("*Save configuration before deploying.*")
    if save_btn.value:
        updated_config = {
            "version": "1.0.0",
            "components": {
                "storage": {
                    "provider": sel_storage,
                    "bucket_name": storage_bucket.value,
                    "port": int(storage_port.value),
                    "volume_size_gb": 10,
                },
                "catalog": {
                    "provider": sel_catalog,
                    "port": int(catalog_port.value),
                    "admin_client_id": "admin",
                    "admin_client_secret": "adminsecret",
                },
                "pipeline": {
                    "provider": sel_ingest,
                    "observe_port": int(vector_observe_port.value),
                    "ingest_port": int(vector_ingest_port.value),
                    "metrics_port": int(vector_metrics_port.value),
                    "vrl_transform": vrl_transform.value,
                    "fluentbit_observe_port": int(fluentbit_observe_port.value),
                    "fluentbit_ingest_port": int(fluentbit_ingest_port.value),
                    "fluentbit_transform": fluentbit_transform.value,
                },
                "query": {"provider": sel_query},
                "schema": {"standard": sel_schema},
            },
        }
        with open(config_path, "w") as _f:
            yaml.safe_dump(updated_config, _f, sort_keys=True)
        save_status = mo.md("**moar-spec.yaml updated.**")
    return (save_status,)


@app.cell(hide_code=True)
def _(mo):
    test_input = mo.ui.text_area(
        value='{"message": "log line", "timestamp": "2026-06-18T12:00:00Z", "user": "admin", "success": true}',
        label="Sample JSON Record In", rows=4,
    )
    test_btn = mo.ui.run_button(label="Validate VRL Transform", kind="success")
    return test_btn, test_input


@app.cell(hide_code=True)
def _(mo, os, subprocess, test_btn, textwrap, vrl_transform):
    test_output = mo.md("*Edit the VRL rule (Configuration tab) and run a validation.*")
    if test_btn.value:
        _vrl = textwrap.indent(vrl_transform.value or "# no-op\n.", "        ")
        _temp_config = (
            "sources:\n"
            "  test_src:\n"
            "    type: stdin\n"
            "\n"
            "transforms:\n"
            "  test_vrl:\n"
            "    type: remap\n"
            '    inputs: ["test_src"]\n'
            "    source: |\n"
            f"{_vrl}\n"
            "\n"
            "sinks:\n"
            "  test_sink:\n"
            "    type: console\n"
            '    inputs: ["test_vrl"]\n'
            "    encoding:\n"
            "      codec: json\n"
        )
        _temp_file = "temp_test_config.yaml"
        with open(_temp_file, "w") as _tf:
            _tf.write(_temp_config)
        try:
            _res = subprocess.run(
                ["vector", "validate", "--no-environment", _temp_file],
                capture_output=True, text=True, timeout=30,
            )
            _ok = _res.returncode == 0
            test_output = mo.md(
                f"**VRL validation {'passed' if _ok else 'failed'}** "
                f"(exit {_res.returncode}):\n```\n{(_res.stdout + _res.stderr).strip()}\n```\n"
                "*`vector validate` type-checks the VRL inside a full pipeline; live record "
                "preview needs a running Vector container (Manage -> Infrastructure).*"
            )
        except FileNotFoundError:
            test_output = mo.md("**Vector binary not found.** Install Vector locally to validate VRL before deploy.")
        except Exception as _e:
            test_output = mo.md(f"**VRL validation error:** {_e}")
        finally:
            if os.path.exists(_temp_file):
                os.remove(_temp_file)
    return (test_output,)


@app.cell(hide_code=True)
def _(mo):
    deploy_btn = mo.ui.run_button(label="Deploy Stack via Pulumi", kind="success")
    destroy_btn = mo.ui.run_button(label="Tear Down Stack", kind="danger")
    gate_override = mo.ui.switch(value=False, label="Override the data-health gate (logged on deploy)")
    return deploy_btn, destroy_btn, gate_override


@app.cell(hide_code=True)
def _(P, cat, config_path, deployer, ev, evidence, gl, layer1, layer3, layer4, mo, os, sel_catalog, sel_ingest, sel_query, sel_schema, sel_storage, ui):
    # The composite data-health gate — the spine of the console. The verdict logic
    # lives in gate_logic.compute_gate (a pure function the proof harnesses exercise
    # through healthy -> broken -> healthy arcs), so this cell only gathers the layer
    # inputs and renders. Config integrity is a HARD deploy gate; Layer 2 is observed;
    # Layers 1/3/4 are MEASURED by their audits and may decay to `stale` (a proven
    # pass that has not been re-validated within its TTL — not-green but not a failure).
    _warns = [t for lvl, t, _b in P.compat_notes(sel_storage, sel_catalog, sel_query, sel_ingest, sel_schema) if lvl == "warn"]
    gate = gl.compute_gate(
        warns=_warns,
        spec_saved=os.path.exists(config_path),
        docker_up=deployer.is_docker_available(),
        catalog_live=cat is not None,
        layer1_status=layer1.get("effective_status", layer1.get("status", "unmeasured")),
        layer3_status=layer3.get("effective_status", layer3.get("status", "unmeasured")),
        layer4_status=layer4.get("effective_status", layer4.get("status", "unmeasured")),
    )

    _verdict, _vcolor = gl.verdict_line(gate)
    _rows = "\n".join(f"- {gl.ICON.get(_s, '⚪')} **{_n}** — {_s}" for _n, _s in gate["layers"])
    _blk = ("\n\n**Blockers:**\n" + "\n".join(f"- {_b}" for _b in gate["blockers"])) if gate["blockers"] else ""
    _unm = ("\n\n*Unproven layers are labeled, never shown as a pass; run the Layer-3 audit "
            "(Strategy Vault → Data Health) to turn it green. A green gate is the deploy/inspect "
            "authorization, not a slide.*") if gate["unmeasured"] else ""
    # Thesis-evidence verbs feed the gate as an informational line, not a blocking
    # layer — they re-prove the pillars on demand and need a live stack to run.
    _evs = ev.summarize(evidence)
    _evline = (f"\n\n*Thesis-evidence verbs: {_evs['passing']} passing / {_evs['total']} run"
               + (f", {_evs['blocked']} blocked" if _evs['blocked'] else "")
               + (f" (last run {_evs['last_run']})" if _evs['last_run'] else "")
               + " — informational, not a gate layer.*") if _evs["total"] else ""
    gate_panel = ui.panel(mo,
        ui.header(mo, "Data-Health Gate"),
        mo.md(f"**<span style='color:{_vcolor}; font-size:1.05rem;'>{_verdict}</span>**"),
        mo.md(_rows + _blk + _unm + _evline),
        **{"border": f"1px solid {_vcolor}"},
    )
    return gate, gate_panel


@app.cell(hide_code=True)
def _(config_path, deploy_btn, deployer, destroy_btn, gate, gate_override, mo, yaml):
    logs = []

    def _log(message):
        logs.append(message)

    def _endpoint(outputs, key):
        item = outputs.get(key) if outputs else None
        return getattr(item, "value", "n/a")

    deployment_status = mo.md("*Deployer idle.*")
    if deploy_btn.value:
        if not gate["deploy_ok"] and not gate_override.value:
            deployment_status = mo.md(
                "**Deploy blocked by the data-health gate.**\n"
                + "\n".join(f"- {_b}" for _b in gate["blockers"])
                + "\n\nClear the blockers above, or toggle **Override the data-health gate** to proceed anyway."
            )
        else:
            if not gate["deploy_ok"] and gate_override.value:
                import datetime as _dt
                _stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                _log(f"[GATE OVERRIDE {_stamp}] deploying despite: {'; '.join(gate['blockers'])}\n")
            with open(config_path, "r") as _f:
                _cfg = yaml.safe_load(_f) or {}
            try:
                _out = deployer.deploy_stack(_cfg, log_callback=_log)
                deployment_status = mo.md(
                    "**Stack deployed.** Endpoints:\n"
                    f"- Storage (S3): {_endpoint(_out, 'storage_endpoint')}\n"
                    f"- Catalog: {_endpoint(_out, 'catalog_endpoint')}\n"
                    f"- Observability: {_endpoint(_out, 'vector_observe')}"
                )
            except deployer.DockerUnavailable as _e:
                deployment_status = mo.md(f"**Not deployed — {_e}**")
            except Exception as _e:
                deployment_status = mo.md(f"**Deployment failed:** {_e}")
    elif destroy_btn.value:
        with open(config_path, "r") as _f:
            _cfg = yaml.safe_load(_f) or {}
        try:
            deployer.destroy_stack(_cfg, log_callback=_log)
            deployment_status = mo.md("**Stack destroyed.**")
        except deployer.DockerUnavailable as _e:
            deployment_status = mo.md(f"**Nothing destroyed — {_e}**")
        except Exception as _e:
            deployment_status = mo.md(f"**Stack destruction failed:** {_e}")
    return deployment_status, logs


@app.cell(hide_code=True)
def _(RestCatalog, catalog_port, sel_catalog, storage_bucket, storage_port):
    cat = None
    catalog_error = None
    if RestCatalog and sel_catalog == "polaris" and catalog_port.value and storage_port.value:
        try:
            cat = RestCatalog(
                "moar_catalog",
                **{
                    "type": "rest",
                    "uri": f"http://localhost:{catalog_port.value}",
                    "warehouse": storage_bucket.value or "moar-warehouse",
                    "s3.endpoint": f"http://localhost:{storage_port.value}",
                    "s3.access-key-id": "aws_access_key",
                    "s3.secret-access-key": "aws_secret_key",
                    "s3.path-style-access": "true",
                    "s3.region": "us-east-1",
                },
            )
        except Exception as e:
            catalog_error = str(e)
    return cat, catalog_error


@app.cell(hide_code=True)
def _(cat, catalog_error, mo, sel_catalog):
    ns_selector = None
    if cat is None:
        if catalog_error:
            ns_selector = mo.md(f"**REST catalog connection error:** `{catalog_error}`. Deploy the stack first.")
        elif sel_catalog != "polaris":
            ns_selector = mo.md("*Live metadata inspection currently supports the Polaris REST catalog.*")
        else:
            ns_selector = mo.md("*REST catalog offline or unconfigured. Deploy the stack to query.*")
    else:
        try:
            _namespaces = cat.list_namespaces()
            if _namespaces:
                _names = [".".join(ns) if isinstance(ns, (list, tuple)) else str(ns) for ns in _namespaces]
                ns_selector = mo.ui.dropdown(options=_names, value=_names[0], label="Select Namespace")
            else:
                ns_selector = mo.md("*No namespaces found. Write data first.*")
        except Exception as e:
            ns_selector = mo.md(f"**Failed to list namespaces:** `{e}`")
    return (ns_selector,)


@app.cell(hide_code=True)
def _(cat, mo, ns_selector):
    table_selector = None
    if cat and ns_selector and hasattr(ns_selector, "value") and isinstance(ns_selector.value, str):
        try:
            _tables = cat.list_tables(tuple(ns_selector.value.split(".")))
            if _tables:
                _names = [".".join(t[1:]) if len(t) > 1 else str(t[0]) for t in _tables]
                table_selector = mo.ui.dropdown(options=_names, value=_names[0], label="Select Iceberg Table")
            else:
                table_selector = mo.md("*No tables found in this namespace.*")
        except Exception as e:
            table_selector = mo.md(f"**Failed to list tables:** `{e}`")
    return (table_selector,)


@app.cell(hide_code=True)
def _(cat, mo, ns_selector, table_selector):
    loaded_table = None
    loaded_table_id = None
    if cat and table_selector and hasattr(table_selector, "value") and isinstance(table_selector.value, str):
        try:
            _id = f"{ns_selector.value}.{table_selector.value}"
            _tbl = cat.load_table(_id)
            loaded_table = _tbl
            loaded_table_id = _id
            import pandas as pd
            _schema_df = pd.DataFrame([
                {"Field": f.name, "Type": str(f.field_type), "Required": "Yes" if f.required else "No"}
                for f in _tbl.schema().fields
            ])
            try:
                _arrow = _tbl.scan().to_arrow()
                _rows = _arrow.num_rows
                # Counts only — never render raw telemetry rows. Real security data
                # is a prompt-injection and control-char surface; the inspector
                # reports field population, not values.
                _fill_df = pd.DataFrame([
                    {"Field": _arrow.field(_i).name,
                     "Non-null": _arrow.num_rows - _arrow.column(_i).null_count,
                     "Null": _arrow.column(_i).null_count}
                    for _i in range(_arrow.num_columns)
                ])
                _summary = mo.as_html(_fill_df)
                _summary_caption = ("##### Field population — counts only "
                                    "(raw rows are not rendered: telemetry is a prompt-injection / control-char surface)")
            except Exception as _scan_err:
                _summary = mo.md(f"*No records yet, or scan failed: {_scan_err}*")
                _summary_caption = "##### Field population"
                _rows = 0
            inspect_output = mo.vstack([
                mo.md(f"#### Table `{_id}` ({_rows} rows)"),
                mo.md("##### Schema"),
                mo.as_html(_schema_df),
                mo.md(_summary_caption),
                _summary,
            ])
        except Exception as e:
            inspect_output = mo.md(f"**Failed to load table metadata:** {e}")
    else:
        inspect_output = mo.md("*Select a namespace and table to inspect.*")
    return inspect_output, loaded_table, loaded_table_id


@app.cell(hide_code=True)
def _(fluentbit_observe_port, mo, sel_ingest, ui, vector_metrics_port):
    import urllib.request

    import vector_metrics as vm

    def _probe(url):
        try:
            with urllib.request.urlopen(url, timeout=0.5) as r:
                return r.status == 200
        except Exception:
            return False

    _counts = (vm.scrape_counts(f"http://localhost:{vector_metrics_port.value}/metrics")
               if "vector" in sel_ingest else None)
    _fluent_up = "fluentbit" in sel_ingest and _probe(f"http://localhost:{fluentbit_observe_port.value}/api/v0/info")
    _vector_up = _counts is not None
    _live = _vector_up or _fluent_up

    _status = "Active (running)" if _live else "Offline"
    _color = "var(--color-teal-500)" if _live else "var(--color-text-muted)"
    if _counts is not None:
        _ein, _eout, _errs = _counts
        _in_s, _out_s, _err_s = f"{_ein:,}", f"{_eout:,}", f"{_errs:,}"
        _hint = (
            f"Real counters scraped from Vector's prometheus_exporter on :{vector_metrics_port.value} "
            "(internal_metrics → component_{received,sent,errors}_total, excluding Vector's own "
            "telemetry plumbing)."
        )
    else:
        _in_s = _out_s = _err_s = "—"
        _hint = (
            "Pipeline live via Fluent Bit; Vector metrics scrape unavailable — counters unmeasured (—), never faked."
            if _live else
            "No Vector metrics scrape — counters unmeasured (shown as —, never faked). Deploy the stack "
            "(Manage → Infrastructure) and confirm the Prometheus metrics port."
        )

    tab_metrics = ui.panel(mo,
        ui.header(mo, "Live Pipeline Telemetry"),
        mo.md(f"**<span style='color:{_color}; font-size:1.1rem;'>● {_status}</span>**"),
        mo.hstack([
            ui.card(mo, ui.header(mo, "Status"), mo.md(f"`{_status}`")),
            ui.card(mo, ui.header(mo, "Events ingested"), mo.md(f"`{_in_s}`")),
            ui.card(mo, ui.header(mo, "Events delivered"), mo.md(f"`{_out_s}`")),
            ui.card(mo, ui.header(mo, "Errors"), mo.md(f"`{_err_s}`")),
        ], gap=2),
        mo.md(f"*{_hint}*"),
    )
    return (tab_metrics,)


@app.cell
def _(mo, sel_schema, P):
    _schema_label = P.label_for(P.SCHEMA, sel_schema)
    health_crc = mo.ui.switch(value=True, label="Parquet CRC checksum integrity (bit-flip audit)")
    health_schema = mo.ui.switch(value=True, label=f"Schema conformity ({_schema_label}) & NULL constraints")
    health_tombstone = mo.ui.switch(value=True, label="DuckLake tombstone silent-resurrection check (#1215)")
    health_orphan = mo.ui.switch(value=True, label="S3/SeaweedFS orphan-file audit (manifest match)")
    health_compaction = mo.ui.switch(value=True, label="Small-file compaction threshold alert (<128MB)")
    run_health = mo.ui.run_button(label="Run Data Health Audits", kind="success")
    okf_search = mo.ui.text(placeholder="Search decisions & assumptions by title, claim, or ID...")
    return health_compaction, health_crc, health_orphan, health_schema, health_tombstone, okf_search, run_health


@app.cell(hide_code=True)
def _(P, mo, okf, sel_catalog, sel_ingest, sel_query, sel_schema, sel_storage, ui, vault_notes):
    # Resolve provenance refs against the loaded OKF bundle. A ref that resolves to
    # a note renders rich (title + tier + confidence + reviewed); a ref that exists
    # only in the hypothesis tracker renders as a plain verified pointer. Every ref
    # is checked to exist — the chip never fabricates a link.
    _by_id = okf.index_by_id(vault_notes)

    def _chip(ref):
        n = _by_id.get(ref)
        if n is None:
            return f"&nbsp;&nbsp;📎 `{ref}` — verified in MASTER-HYPOTHESIS-TRACKER.md"
        fm = n.frontmatter
        title = n.title or str(fm.get("claim", ""))[:90]
        tier = fm.get("evidence-level") or fm.get("basis") or "?"
        conf = fm.get("confidence", "?")
        reviewed = fm.get("last_reviewed") or fm.get("updated") or ""
        tail = f", reviewed {reviewed}" if reviewed else ""
        return f"&nbsp;&nbsp;📎 `{ref}` — {title} (Tier {tier}, confidence {conf}{tail}) · `{n.path.name}`"

    def _doc(group, code):
        p = P.find(group, code)
        if not p:
            return None
        lines = [f"**{p.label}**", f"*Pros:* {p.pros}", f"*Cons:* {p.cons}"]
        if p.swap_cost:
            lines.append(f"*Swap cost (reversibility):* {p.swap_cost}")
        if p.claims:
            lines.append("*Provenance:*")
            lines.extend(_chip(c) for c in p.claims)
        return mo.md("  \n".join(lines))

    _blocks = [
        _doc(P.STORAGE, sel_storage),
        _doc(P.CATALOG, sel_catalog),
        *[_doc(P.INGEST, c) for c in sel_ingest],
        *[_doc(P.QUERY, c) for c in sel_query],
        _doc(P.SCHEMA, sel_schema),
    ]
    docs_panel = ui.panel(mo,
        ui.header(mo, "Selected components — pros, cons, reversibility & provenance"),
        *[b for b in _blocks if b is not None],
        mo.md("*Swap cost = what swapping that component out costs (a config change vs. a data re-land). "
              "Provenance chips tie the pick to a sourced assumption/hypothesis — the public method, "
              "not the paid per-vendor Matrix score. Deep dives: "
              "[securitydataworks.com/writing](https://securitydataworks.com/writing) · "
              "[Matrix](https://securitydataworks.com/matrix)*"),
    )
    return (docs_panel,)


@app.cell(hide_code=True)
def _(mo):
    import paid_scoring as paid
    archetype_selector = mo.ui.dropdown(
        options=["A", "B", "C"], value="A", label="Capability Matrix archetype")
    return archetype_selector, paid


@app.cell(hide_code=True)
def _(P, archetype_selector, mo, paid, sel_catalog, sel_ingest, sel_query, ui):
    # The paid Capability Matrix scorecard. PAID_MODE off (the public default, and what
    # any clone gets) shows NO scores. PAID_MODE on loads the named per-criterion 1-5
    # scores from the private vault (never this repo) for the consultant's live delivery.
    if not paid.paid_mode():
        scorecard_panel = ui.panel(mo,
            ui.header(mo, "Capability Matrix scores — paid tier (not shown)"),
            mo.md(
                "Per-criterion 1-5 scores, weighted archetype totals, and claim-vs-shipped "
                "deltas are paid SDW IP and are **not** rendered in the public console. Run with "
                "`MOAR_PAID_MODE=1` (scores load from the private vault, never this repo) for the "
                "scored view, or see the public codeworded summary at "
                "[securitydataworks.com/matrix](https://securitydataworks.com/matrix)."),
        )
    else:
        _arch = archetype_selector.value
        try:
            _scores = paid.load_scores(_arch)
            _err = None
        except paid.PaidScoreLeak as _e:
            _scores, _err = {}, str(_e)
        _sel = ([("query", c) for c in sel_query]
                + [("catalog", sel_catalog)]
                + [("ingest", c) for c in sel_ingest])
        _groups = {"query": P.QUERY, "catalog": P.CATALOG, "ingest": P.INGEST}
        _blocks = []
        for _cat, _code in _sel:
            _lbl = P.label_for(_groups[_cat], _code)
            _rec = paid.find(_scores, _lbl)
            if not _rec:
                _blocks.append(mo.md(f"**{_lbl}** — *not scored for archetype {_arch}.*"))
                continue
            import pandas as _pd
            _df = _pd.DataFrame([
                {"Criterion": _c["name"], "Score": _c["score"],
                 "Weight": _c["weight"], "Tier": _c["tier"]}
                for _c in _rec["criteria"]
            ])
            _blocks.append(mo.vstack([
                mo.md(f"**{_lbl}** — weighted **{_rec['weighted']}/5** (archetype {_arch})"),
                mo.as_html(_df),
            ]))
        scorecard_panel = ui.panel(mo,
            ui.header(mo, f"Capability Matrix scores — PAID MODE · archetype {_arch}"),
            mo.md("⚠️ **Paid IP** — for the consultant's live delivery only; not a public surface. "
                  "The public Matrix shows codeworded scores; this shows the named detail."),
            *([mo.md(f"*Score-source error: {_err}*")] if _err else []),
            archetype_selector,
            *_blocks,
            **{"border": "1px solid var(--color-orange-500)"},
        )
    return (scorecard_panel,)


@app.cell(hide_code=True)
def _(VAULT_PATH, okf):
    # Read the project1 strategy vault as an OKF bundle (decisions + assumptions).
    try:
        vault_notes = okf.load_bundle(
            VAULT_PATH,
            subdirs=["02-projects/securitydataworks/decisions",
                     "02-projects/securitydataworks/assumptions",
                     "01-knowledge-base/hypotheses",
                     "01-knowledge-base/contradictions"],
        )
        vault_error = None
    except Exception as _e:  # noqa: BLE001 - surface any read failure to the UI
        vault_notes = []
        vault_error = str(_e)
    return vault_error, vault_notes


@app.cell(hide_code=True)
def _(mo, okf, okf_search, ui, vault_error, vault_notes):
    _mdrs = okf.search([n for n in vault_notes if n.type == "MDR"], okf_search.value)
    _asms = okf.search([n for n in vault_notes if n.type == "Assumption"], okf_search.value)

    def _mdr_line(n):
        fm = n.frontmatter
        return f"- **{n.id}** — {n.title} (`{fm.get('status', '?')}`, `{fm.get('date', '')}`) · `{n.path.name}`"

    def _asm_line(n):
        fm = n.frontmatter
        claim = str(fm.get("claim", n.title))
        claim = claim[:140] + "…" if len(claim) > 140 else claim
        return f"- **{n.id}** — {claim} (confidence `{fm.get('confidence', '?')}`, reviewed `{fm.get('last_reviewed', '')}`)"

    _intro = (
        "This panel reads the project1 strategy vault as a **Google Open Knowledge Format "
        "(OKF v0.1)** bundle — a directory of markdown files whose `type:` frontmatter and "
        "`[[wikilinks]]` form a knowledge graph (Google Cloud, published 2026-06-12). "
        "Decisions (`MDR-xxxx`) and Assumptions (`A-xx`) are read straight off disk by "
        "`okf_reader`, so the stack you pick above stays coupled to the recorded *why*. "
        "Tolaria indexes this same vault for the agent host; this app reads the files "
        "directly rather than through Tolaria's read-only MCP server."
    )

    if vault_error:
        okf_panel = ui.panel(mo, ui.header(mo, "Strategy Vault (OKF)"),
                             mo.md(f"*Vault unreadable: {vault_error}. Set `VAULT_PATH` to the project1 root.*"))
    else:
        okf_panel = ui.panel(mo,
            ui.header(mo, "Architecture Strategy & OKF Vault"),
            mo.md(_intro),
            mo.hstack([mo.md("**Search vault:**"), okf_search], align="center", gap=2),
            mo.md(f"**Decision Records (MDRs)** — {len(_mdrs)} match:"),
            mo.md("\n".join(_mdr_line(n) for n in _mdrs[:10]) if _mdrs else "*No matching MDRs.*"),
            mo.md(f"**Strategic Assumptions** — {len(_asms)} match:"),
            mo.md("\n".join(_asm_line(n) for n in _asms[:10]) if _asms else "*No matching assumptions.*"),
        )
    return (okf_panel,)


@app.cell(hide_code=True)
def _(mo):
    # Persist the last Layer-3 audit result so the gate holds its verdict across
    # reactive ticks (the run-button only fires for one cycle). The runner cell
    # writes; the reader cell publishes `layer3` for the gate and health panel.
    get_layer3, set_layer3 = mo.state({"status": "unmeasured", "checks": [], "table": None})
    return get_layer3, set_layer3


@app.cell(hide_code=True)
def _(
    health_compaction,
    health_crc,
    health_orphan,
    health_schema,
    health_tombstone,
    l3,
    loaded_table,
    loaded_table_id,
    run_health,
    set_layer3,
    storage_bucket,
    storage_port,
):
    # The Layer-3 audit runner. Runs only when the audit button fires AND a table is
    # loaded; computes the real audit and stores it. It never runs reactively on
    # every keystroke (it does manifest + object-store I/O), and never fabricates a
    # result — if it cannot list the store, the orphan check reports unmeasured.
    if run_health.value and loaded_table is not None:
        _enabled = set()
        if health_compaction.value:
            _enabled.add("small_files")
        if health_orphan.value:
            _enabled.add("orphans")
        if health_schema.value:
            _enabled.add("schema_conformance")
        if health_crc.value:
            _enabled.add("crc")
        if health_tombstone.value:
            _enabled.add("tombstone")

        # The orphan diff needs the parquet basenames under this table's data prefix
        # in the object store. Derive the key prefix from the table location; on any
        # failure the lister returns None and the orphan check degrades honestly.
        _store = None
        if health_orphan.value:
            try:
                _loc = loaded_table.location()  # e.g. s3://bucket/ns/table
                _prefix = _loc.split("/", 3)[3] if _loc.count("/") >= 3 else ""
                _store = l3.list_s3_parquet_basenames(
                    f"http://localhost:{storage_port.value}",
                    storage_bucket.value or "moar-warehouse",
                    _prefix,
                    "aws_access_key", "aws_secret_key",
                )
            except Exception:
                _store = None

        _result = l3.audit_table(loaded_table, store_basenames=_store, enabled=_enabled)
        _result["table"] = loaded_table_id
        import datetime as _dt
        _result["ran_at"] = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        set_layer3(_result)
    return


@app.cell(hide_code=True)
def _(dk, get_layer3):
    import datetime as _dt
    _l3 = get_layer3()
    layer3 = dict(_l3)
    layer3["effective_status"] = dk.effective_status(
        _l3.get("status", "unmeasured"), _l3.get("ran_at"),
        _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), dk.DEFAULT_TTL_SECONDS)
    return (layer3,)


@app.cell(hide_code=True)
def _(gl, layer3, loaded_table_id, mo, ui):
    # Render the Layer-3 audit result. Honest empty/stale states: nothing measured
    # until you run it; a note when the stored verdict is for a different table.
    _checks = layer3.get("checks", [])
    if not _checks:
        health_panel = ui.panel(mo,
            ui.header(mo, "Layer 3 — data-quality audit"),
            mo.md("*No audit run yet. Deploy the stack, land data, pick a table in the Metadata "
                  "Inspector, then press **Run Data Health Audits**. Until then the gate treats "
                  "Layer 3 as unproven — it never shows an unrun check as a pass.*"),
        )
    else:
        _lines = []
        for _c in _checks:
            _m = ", ".join(f"{_k}={_v}" for _k, _v in (_c.measured or {}).items())
            _lines.append(f"- {gl.ICON.get(_c.status, '⚪')} **{_c.name}** ({_c.status}) — {_c.detail}"
                          + (f"  \n&nbsp;&nbsp;`{_m}`" if _m else ""))
        _stale = ("" if layer3.get("table") in (None, loaded_table_id)
                  else f"\n\n*Verdict is for `{layer3.get('table')}`; re-run for the selected table.*")
        _status = layer3.get("status", "unmeasured")
        _color = {"pass": "var(--color-teal-500)", "fail": "#c14a4a"}.get(_status, "var(--color-orange-500)")
        health_panel = ui.panel(mo,
            ui.header(mo, "Layer 3 — data-quality audit (measured)"),
            mo.md(f"**<span style='color:{_color};'>Layer 3 status: {_status}</span>** "
                  f"· table `{layer3.get('table')}`"),
            mo.md("\n".join(_lines) + _stale),
            mo.md("*Tier B, single host. `crc` and `tombstone` are reported as unwired — no machinery "
                  "yet, so they are never counted as a pass. Freshness, small-files, orphans, and schema "
                  "conformance are measured against the live catalog and object store.*"),
            **{"border": f"1px solid {_color}"},
        )
    return (health_panel,)


@app.cell(hide_code=True)
def _(ev, mo):
    evidence_select = mo.ui.multiselect(
        options=[v["verb"] for v in ev.VERBS],
        value=["verify"],
        label="Evidence verbs (each re-proves a thesis claim against the live stack)")
    run_evidence = mo.ui.run_button(label="Run Evidence Verbs", kind="success")
    return evidence_select, run_evidence


@app.cell(hide_code=True)
def _(mo):
    # Persist the last evidence-verb run so the gate's informational line and the
    # panel survive reactive ticks (the run-button fires for one cycle).
    get_evidence, set_evidence = mo.state([])
    return get_evidence, set_evidence


@app.cell(hide_code=True)
def _(deployer, ev, evidence_select, os, run_evidence, set_evidence):
    # Run the selected ./moar verbs only on the button press, gated on a reachable
    # Docker daemon — verbs degrade to "blocked" otherwise, never a fabricated pass.
    # Output is bounded + sanitized inside evidence_runner (telemetry-injection rule).
    if run_evidence.value and evidence_select.value:
        import datetime as _dt
        _now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _avail = deployer.is_docker_available()
        _docker_dir = os.path.abspath("..")  # ./moar lives in docker/, app runs in docker/control-plane
        _results = [ev.run_verb(_v, docker_dir=_docker_dir, available=_avail, now_iso=_now)
                    for _v in evidence_select.value]
        set_evidence(_results)
    return


@app.cell(hide_code=True)
def _(get_evidence):
    evidence = get_evidence()
    return (evidence,)


@app.cell(hide_code=True)
def _(ev, evidence, mo, ui):
    _ic = {"pass": "🟢", "fail": "🔴", "blocked": "⚪", "error": "🟠"}
    if not evidence:
        evidence_panel = ui.panel(mo,
            ui.header(mo, "Thesis-evidence verbs (./moar)"),
            mo.md("*Select verbs and press **Run Evidence Verbs**. Each shells out to a "
                  "`./moar` verb that re-proves a thesis claim against the live stack — "
                  "answer-equality, the four portability (swap) proofs, and the single-"
                  "hypothesis checks. With no Docker daemon they report `blocked`, never a "
                  "fabricated pass.*"),
        )
    else:
        _s = ev.summarize(evidence)
        _lines = [
            f"- {_ic.get(_r['status'], '⚪')} **{_r['verb']}** ({_r['status']}) · `{_r['hypothesis']}` — "
            + ((_r['summary'].splitlines() or [''])[-1])
            for _r in evidence
        ]
        evidence_panel = ui.panel(mo,
            ui.header(mo, "Thesis-evidence verbs (./moar) — measured"),
            mo.md(f"**{_s['passing']} passing · {_s['failing']} failing · {_s['blocked']} blocked · "
                  f"{_s['errored']} error** · last run `{_s['last_run']}` · Tier B, single host"),
            mo.md("\n".join(_lines)),
            mo.accordion({
                f"{_r['verb']} — bounded output":
                mo.Html(f"<pre style='max-height:200px;overflow:auto;'>{_r['summary']}</pre>")
                for _r in evidence}),
        )
    return (evidence_panel,)


# ----- Layer 1 — source health ----------------------------------------------
@app.cell(hide_code=True)
def _(cat, ns_selector):
    # Cheap: list the source table NAMES in the selected namespace for the Layer 1/4
    # selectors. load_table is deferred to the audit runners (on button press), so
    # picking a namespace does not trigger a metadata load for every table in it.
    ns_table_names = []
    if cat and ns_selector and hasattr(ns_selector, "value") and isinstance(ns_selector.value, str):
        try:
            for _t in cat.list_tables(tuple(ns_selector.value.split("."))):
                ns_table_names.append(".".join(_t[1:]) if len(_t) > 1 else str(_t[0]))
        except Exception:
            ns_table_names = []
    return (ns_table_names,)


@app.cell(hide_code=True)
def _(mo):
    get_layer1, set_layer1 = mo.state({"status": "unmeasured", "sources": [], "ran_at": None})
    return get_layer1, set_layer1


@app.cell(hide_code=True)
def _(mo):
    capture_baseline = mo.ui.run_button(label="Capture source baseline (enables completeness)")
    return (capture_baseline,)


@app.cell(hide_code=True)
def _(cat, l1, ns_selector, ns_table_names, run_health, set_layer1):
    # Runs on the same button as Layer 3, across all sources in the namespace. Tables are
    # loaded HERE (on the button press), not on namespace selection. Loads the baseline
    # sidecar if present (else completeness reads PENDING). Never fabricates.
    if run_health.value and ns_table_names and cat and isinstance(getattr(ns_selector, "value", None), str):
        import datetime as _dt
        _tables = {}
        for _n in ns_table_names:
            try:
                _tables[_n] = cat.load_table(f"{ns_selector.value}.{_n}")
            except Exception:
                continue
        if _tables:
            _now_ms = int(_dt.datetime.now(_dt.timezone.utc).timestamp() * 1000)
            _res = l1.audit_sources(_tables, now_ms=_now_ms, baseline=l1.load_baseline("layer1-baseline.json"))
            _res["ran_at"] = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            _res["namespace"] = ns_selector.value
            set_layer1(_res)
    return


@app.cell(hide_code=True)
def _(capture_baseline, cat, l1, mo, ns_selector, ns_table_names):
    baseline_status = mo.md("")
    if capture_baseline.value and ns_table_names and cat and isinstance(getattr(ns_selector, "value", None), str):
        _tables = {}
        for _n in ns_table_names:
            try:
                _tables[_n] = cat.load_table(f"{ns_selector.value}.{_n}")
            except Exception:
                continue
        _counts = l1.source_row_counts(_tables)
        l1.save_baseline("layer1-baseline.json", _counts)
        baseline_status = mo.md(f"**Baseline captured** for {len(_counts)} source(s) — completeness "
                                "is measured on the next audit.")
    return (baseline_status,)


@app.cell(hide_code=True)
def _(dk, get_layer1):
    import datetime as _dt
    _l1 = get_layer1()
    layer1 = dict(_l1)
    layer1["effective_status"] = dk.effective_status(
        _l1.get("status", "unmeasured"), _l1.get("ran_at"),
        _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), dk.DEFAULT_TTL_SECONDS)
    return (layer1,)


@app.cell(hide_code=True)
def _(baseline_status, gl, layer1, mo, ns_selector, ui):
    _srcs = layer1.get("sources", [])
    _cur_ns = getattr(ns_selector, "value", None)
    _stale_note = ("" if layer1.get("namespace") in (None, _cur_ns)
                   else f"\n\n*Verdict is for namespace `{layer1.get('namespace')}`; re-run for `{_cur_ns}`.*")
    if not _srcs:
        layer1_panel = ui.panel(mo,
            ui.header(mo, "Layer 1 — source health"),
            mo.md("*No sources audited yet. Deploy the stack, land data, select a namespace in the "
                  "Metadata Inspector, then press **Run Data Health Audits**. With no baseline, "
                  "completeness reads PENDING — you can't measure a drop with nothing to compare to.*"),
            baseline_status,
        )
    else:
        _eff = layer1.get("effective_status", layer1.get("status"))
        _color = {"pass": "var(--color-teal-500)", "fail": "#c14a4a",
                  "stale": "var(--color-orange-500)"}.get(_eff, "var(--color-orange-500)")
        _lines = []
        for _s in _srcs:
            _c = _s.get("completeness") or {}
            _fresh = next((c for c in _s["checks"] if c.name == "freshness"), None)
            _lines.append(f"- {gl.ICON.get(_s['status'], '⚪')} **{_s['name']}** ({_s['status']}) — "
                          f"{_s.get('rows', '?')} rows · completeness {_c.get('status', '?')}"
                          + (f" · {_fresh.detail}" if _fresh else ""))
        layer1_panel = ui.panel(mo,
            ui.header(mo, "Layer 1 — source health (measured)"),
            mo.md(f"**<span style='color:{_color};'>Layer 1 status: {_eff}</span>** · "
                  f"last run `{layer1.get('ran_at')}`"),
            mo.md("\n".join(_lines) + _stale_note),
            baseline_status,
            mo.md(f"*{layer1.get('label', '')}: a source that never sent and one dropped upstream look "
                  "identical here. Completeness compares to a captured baseline; freshness/conformance "
                  "are measured now. Tier B, single host.*"),
            **{"border": f"1px solid {_color}"},
        )
    return (layer1_panel,)


# ----- Layer 4 — cross-tool gap ---------------------------------------------
@app.cell(hide_code=True)
def _(mo, ns_table_names):
    _names = sorted(ns_table_names)
    l4_sources_select = mo.ui.multiselect(
        options=_names, value=_names[:3],
        label="Inventory sources (>=2 tables sharing an identity column)")
    l4_primary = mo.ui.dropdown(
        options=_names or ["(no tables)"], value=(_names[0] if _names else "(no tables)"),
        label="Authoritative (primary) source")
    l4_idcol = mo.ui.text(value="asset_id", label="Identity column")
    l4_tolerance = mo.ui.number(start=0, stop=1000000, value=0, label="Coverage tolerance (max allowed gap)")
    run_layer4 = mo.ui.run_button(label="Run Cross-Tool Gap", kind="success")
    return l4_idcol, l4_primary, l4_sources_select, l4_tolerance, run_layer4


@app.cell(hide_code=True)
def _(mo):
    get_layer4, set_layer4 = mo.state({"status": "unmeasured", "gaps": [], "ran_at": None})
    return get_layer4, set_layer4


@app.cell(hide_code=True)
def _(cat, l4, l4_idcol, l4_primary, l4_sources_select, l4_tolerance, ns_selector, run_layer4, set_layer4):
    # Load only the selected source tables (on the button press), extract the identity
    # column per source (one column only; values are never rendered), and compute coverage
    # gaps from the primary. Needs >=2 selected sources.
    if run_layer4.value and len(l4_sources_select.value) >= 2 and cat and isinstance(getattr(ns_selector, "value", None), str):
        import datetime as _dt
        _idcol = (l4_idcol.value or "asset_id").strip()
        _sources = {}
        for _n in l4_sources_select.value:
            try:
                _t = cat.load_table(f"{ns_selector.value}.{_n}")
            except Exception:
                _t = None
            _sources[_n] = l4.extract_ids(_t, _idcol) if _t is not None else None
        _res = l4.cross_tool_gap(l4_primary.value, _sources, tolerance=int(l4_tolerance.value or 0))
        _res["ran_at"] = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        _res["sources_sig"] = sorted(l4_sources_select.value)
        set_layer4(_res)
    return


@app.cell(hide_code=True)
def _(dk, get_layer4):
    import datetime as _dt
    _l4 = get_layer4()
    layer4 = dict(_l4)
    layer4["effective_status"] = dk.effective_status(
        _l4.get("status", "unmeasured"), _l4.get("ran_at"),
        _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), dk.DEFAULT_TTL_SECONDS)
    return (layer4,)


@app.cell(hide_code=True)
def _(l4_primary, l4_sources_select, layer4, mo, ui):
    _gaps = layer4.get("gaps", [])
    _status = layer4.get("status", "unmeasured")
    _cur_sig = sorted(l4_sources_select.value)
    _stale_note = ("" if (layer4.get("sources_sig") in (None, _cur_sig)
                          and layer4.get("primary") in (None, l4_primary.value))
                   else "\n\n*Verdict is for a different source set / primary; re-run for the current selection.*")
    if _status == "unmeasured" and not _gaps:
        layer4_panel = ui.panel(mo,
            ui.header(mo, "Layer 4 — cross-tool gap analysis"),
            mo.md("*Pick >=2 inventory tables, an authoritative primary source, and the shared "
                  "identity column, then **Run Cross-Tool Gap**. Exact-match set membership only — "
                  "not entity resolution (deferred). Counts only; identities are never rendered.*"),
        )
    else:
        _eff = layer4.get("effective_status", _status)
        _color = {"pass": "var(--color-teal-500)", "fail": "#c14a4a",
                  "stale": "var(--color-orange-500)"}.get(_eff, "var(--color-orange-500)")
        _primary = layer4.get("primary")
        _lines = [f"- {'🔴' if g['over_tolerance'] else '🟢'} **{_primary} → {g['to']}**: "
                  f"{g['gap_count']} asset(s) in {_primary} missing from {g['to']} "
                  f"({g['primary_count']} vs {g['to_count']})" for g in _gaps]
        layer4_panel = ui.panel(mo,
            ui.header(mo, "Layer 4 — cross-tool gap analysis (measured)"),
            mo.md(f"**<span style='color:{_color};'>Layer 4 status: {_eff}</span>** · "
                  f"primary `{_primary}` · tolerance {layer4.get('tolerance')} · "
                  f"last run `{layer4.get('ran_at')}`"),
            mo.md(("\n".join(_lines) if _lines else "*No gaps computed.*") + _stale_note),
            mo.md(f"*{layer4.get('note', '')}. Counts only — identities are not rendered "
                  "(telemetry-injection rule). Tier B, single host.*"),
            **{"border": f"1px solid {_color}"},
        )
    return (layer4_panel,)


@app.cell(hide_code=True)
def _(capture_baseline, docs_panel, evidence_panel, evidence_select, health_compaction, health_crc, health_orphan, health_panel, health_schema, health_tombstone, l4_idcol, l4_primary, l4_sources_select, l4_tolerance, layer1_panel, layer4_panel, mo, okf_panel, run_evidence, run_health, run_layer4, scorecard_panel, ui):
    # Startup › Strategy — OKF strategy vault + paid Matrix scorecard + thesis-evidence proof
    strategy_view = mo.vstack([
        okf_panel,
        mo.hstack([docs_panel], gap=2),
        scorecard_panel,
        ui.panel(mo,
            ui.header(mo, "Thesis Evidence Runner"),
            mo.md("Re-prove the thesis pillars on demand: each verb runs a `./moar` command "
                  "against the live stack and reports a dated, Tier-B result (bounded output "
                  "only — never raw rows)."),
            evidence_select,
            mo.hstack([run_evidence]),
            evidence_panel,
        ),
    ])
    # Flow › Health — source health (Layer 1) + data quality (Layer 3) + cross-tool coverage (Layer 4)
    health_view = mo.vstack([
        ui.panel(mo,
            ui.header(mo, "Data Health & Schema Validation (Layers 1 & 3)"),
            mo.md("Run the data-quality audit (Layer 3, on the selected table) and the source-health "
                  "audit (Layer 1, across the namespace's sources) together:"),
            mo.hstack([
                mo.vstack([health_crc, health_schema]),
                mo.vstack([health_tombstone, health_orphan]),
                mo.vstack([health_compaction]),
            ], gap=3),
            mo.hstack([run_health, capture_baseline]),
            health_panel,
            layer1_panel,
        ),
        ui.panel(mo,
            ui.header(mo, "Cross-Tool Gap Analysis (Layer 4)"),
            mo.md("Coverage gaps from an authoritative inventory source to the other tools — "
                  "exact-match set membership only (entity resolution deferred):"),
            mo.hstack([l4_sources_select, l4_primary], gap=2),
            mo.hstack([l4_idcol, l4_tolerance], gap=2),
            mo.hstack([run_layer4]),
            layer4_panel,
        ),
    ])
    return (health_view, strategy_view)


@app.cell(hide_code=True)
def _(
    cat,
    config_panel,
    deploy_btn,
    deployment_status,
    destroy_btn,
    gate_override,
    gate_panel,
    health_view,
    inspect_output,
    logs,
    mo,
    ns_selector,
    save_btn,
    save_status,
    selector_panel,
    strategy_view,
    tab_metrics,
    table_selector,
    test_btn,
    test_input,
    test_output,
    ui,
    warnings_panel,
):
    # ── STARTUP ── pick the stack, configure it, and the strategy surface (OKF + Matrix) ──
    tab_pick = mo.vstack([selector_panel, warnings_panel])

    tab_config = mo.vstack([
        config_panel,
        mo.hstack([save_btn, save_status]),
        ui.panel(mo,
            ui.header(mo, "VRL Testing Console"),
            mo.md("Validate Vector transform rules before provisioning them in the container."),
        ),
        test_input,
        mo.hstack([test_btn]),
        test_output,
        ui.panel(mo,
            ui.header(mo, "Infrastructure Lifecycle Manager"),
            mo.md("Spin up or tear down the selected MOAr stack locally in Docker via Pulumi. "
                  "The data-health gate below authorizes the deploy."),
        ),
        gate_panel,
        mo.hstack([deploy_btn, destroy_btn, gate_override]),
        deployment_status,
        mo.accordion({"Deployment Execution Logs":
                      mo.Html(f"<pre style='max-height:250px; overflow-y:auto;'>{''.join(logs)}</pre>")}),
    ])

    startup_tabs = mo.ui.tabs({
        "Pick components": tab_pick,
        "Setup config": tab_config,
        "Strategy": strategy_view,
    })

    # ── FLOW ── land (topology) · health (source + flow + data-quality) · migrate (intent) ──
    tab_land = ui.panel(mo,
        ui.header(mo, "Land — pipeline topology"),
        mo.md("*(planned)* The active flows as a **sources → transforms → sinks** canvas — a "
              "node-edge graph (NiFi / Cribl / Vector-topology style) with a status dot per node and "
              "throughput on each edge. Renders the selected components + the live Vector topology."),
    )
    tab_health = mo.vstack([health_view, tab_metrics])
    tab_migrate = ui.panel(mo,
        ui.header(mo, "Migrate — intent-driven"),
        mo.md("*(planned)* Pick a migration **intent**; the panel expands to focused direction for it "
              "(progressive disclosure, cockpit-style). The swap-cost / migration-cockpit work routes here."),
    )
    flow_tabs = mo.ui.tabs({
        "Land": tab_land,
        "Health": tab_health,
        "Migrate": tab_migrate,
    })

    # ── ANALYZE ── a separate pane for log/telemetry analysis (+ catalog inspection) ──
    _inspector_selectors = (mo.hstack([ns_selector, table_selector])
                            if (cat and hasattr(ns_selector, "value")) else ns_selector)
    tab_analyze = mo.vstack([
        ui.panel(mo,
            ui.header(mo, "Analyze — log analysis"),
            mo.md("*(planned)* Log / telemetry analysis pane (the OCSF marimo-hunt workflow routes here). "
                  "Aggregate output only — never raw rows."),
        ),
        ui.panel(mo,
            ui.header(mo, "Iceberg Metadata Inspector"),
            mo.md("List tables and inspect schema/field population from the active REST catalog "
                  "(counts only — raw rows are never rendered)."),
        ),
        gate_panel,
        _inspector_selectors,
        inspect_output,
    ])

    dashboard = mo.ui.tabs({"Startup": startup_tabs, "Flow": flow_tabs, "Analyze": tab_analyze})
    dashboard
    return


if __name__ == "__main__":
    app.run()
