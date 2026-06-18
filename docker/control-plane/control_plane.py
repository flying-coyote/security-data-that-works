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

    # Tolaria convention: point VAULT_PATH at the OKF vault (project1).
    VAULT_PATH = os.environ.get("VAULT_PATH", os.path.expanduser("~/project1"))
    return P, RestCatalog, VAULT_PATH, deployer, mo, okf, os, subprocess, textwrap, ui, yaml


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
            mo.hstack([vector_ingest_port, vector_observe_port]),
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
    return deploy_btn, destroy_btn


@app.cell(hide_code=True)
def _(config_path, deploy_btn, deployer, destroy_btn, mo, yaml):
    logs = []

    def _log(message):
        logs.append(message)

    def _endpoint(outputs, key):
        item = outputs.get(key) if outputs else None
        return getattr(item, "value", "n/a")

    deployment_status = mo.md("*Deployer idle.*")
    if deploy_btn.value:
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
        except Exception as _e:
            deployment_status = mo.md(f"**Deployment failed:** {_e}")
    elif destroy_btn.value:
        with open(config_path, "r") as _f:
            _cfg = yaml.safe_load(_f) or {}
        try:
            deployer.destroy_stack(_cfg, log_callback=_log)
            deployment_status = mo.md("**Stack destroyed.**")
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
    if cat and table_selector and hasattr(table_selector, "value") and isinstance(table_selector.value, str):
        try:
            _id = f"{ns_selector.value}.{table_selector.value}"
            _tbl = cat.load_table(_id)
            import pandas as pd
            _schema_df = pd.DataFrame([
                {"Field": f.name, "Type": str(f.field_type), "Required": "Yes" if f.required else "No"}
                for f in _tbl.schema().fields
            ])
            try:
                _arrow = _tbl.scan().to_arrow()
                _preview = mo.as_html(_arrow.to_pandas().tail(10))
                _rows = _arrow.num_rows
            except Exception as _scan_err:
                _preview = mo.md(f"*No records yet, or scan failed: {_scan_err}*")
                _rows = 0
            inspect_output = mo.vstack([
                mo.md(f"#### Table `{_id}` ({_rows} rows)"),
                mo.md("##### Schema"),
                mo.as_html(_schema_df),
                mo.md("##### Last 10 records"),
                _preview,
            ])
        except Exception as e:
            inspect_output = mo.md(f"**Failed to load table metadata:** {e}")
    else:
        inspect_output = mo.md("*Select a namespace and table to inspect.*")
    return (inspect_output,)


@app.cell(hide_code=True)
def _(fluentbit_observe_port, mo, sel_ingest, ui, vector_observe_port):
    import urllib.request

    def _probe(url):
        try:
            with urllib.request.urlopen(url, timeout=0.5) as r:
                return r.status == 200
        except Exception:
            return False

    _vector_up = "vector" in sel_ingest and _probe(f"http://localhost:{vector_observe_port.value}/health")
    _fluent_up = "fluentbit" in sel_ingest and _probe(f"http://localhost:{fluentbit_observe_port.value}/api/v0/info")
    _live = _vector_up or _fluent_up

    _status = "Active (running)" if _live else "Offline"
    _color = "var(--color-teal-500)" if _live else "var(--color-text-muted)"
    _counter = "(wire Vector's Prometheus sink to populate counters)" if _live else "—"
    _hint = (
        "Liveness probe only — event/error counters need Vector's Prometheus sink (not wired in this POC)."
        if _live else
        "Deploy the stack (Manage -> Infrastructure) to bring the pipeline online."
    )

    tab_metrics = ui.panel(mo,
        ui.header(mo, "Live Pipeline Telemetry"),
        mo.md(f"**<span style='color:{_color}; font-size:1.1rem;'>● {_status}</span>**"),
        mo.hstack([
            ui.card(mo, ui.header(mo, "Status"), mo.md(f"`{_status}`")),
            ui.card(mo, ui.header(mo, "Events ingested"), mo.md(f"`{_counter}`")),
            ui.card(mo, ui.header(mo, "Errors"), mo.md("`—`")),
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
def _(P, mo, sel_catalog, sel_ingest, sel_query, sel_schema, sel_storage, ui):
    def _doc(group, code):
        p = P.find(group, code)
        if not p:
            return None
        return mo.md(f"**{p.label}**  \n*Pros:* {p.pros}  \n*Cons:* {p.cons}")

    _blocks = [
        _doc(P.STORAGE, sel_storage),
        _doc(P.CATALOG, sel_catalog),
        *[_doc(P.INGEST, c) for c in sel_ingest],
        *[_doc(P.QUERY, c) for c in sel_query],
        _doc(P.SCHEMA, sel_schema),
    ]
    docs_panel = ui.panel(mo,
        ui.header(mo, "Selected components — pros & cons (from the Capability Matrix)"),
        *[b for b in _blocks if b is not None],
        mo.md("*Deep dives: [securitydataworks.com/writing](https://securitydataworks.com/writing) · "
              "Matrix: [securitydataworks.com/matrix](https://securitydataworks.com/matrix)*"),
    )
    return (docs_panel,)


@app.cell(hide_code=True)
def _(VAULT_PATH, okf):
    # Read the project1 strategy vault as an OKF bundle (decisions + assumptions).
    try:
        vault_notes = okf.load_bundle(
            VAULT_PATH,
            subdirs=["02-projects/securitydataworks/decisions",
                     "02-projects/securitydataworks/assumptions"],
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
def _(
    health_compaction,
    health_crc,
    health_orphan,
    health_schema,
    health_tombstone,
    mo,
    run_health,
    sel_schema,
    ui,
    P,
):
    _checks = [
        (health_crc.value, "Parquet CRC checksum", "recompute each file's CRC and compare to the manifest to catch bit-flips"),
        (health_schema.value, f"Schema conformity ({P.label_for(P.SCHEMA, sel_schema)})", "validate columns against the schema and flag NULLs in required fields"),
        (health_tombstone.value, "Tombstone audit (#1215)", "check no deleted rows resurrected via the DuckLake/Postgres delete-conflict bug"),
        (health_orphan.value, "S3 orphan audit", "diff object-store keys against the catalog manifest registry"),
        (health_compaction.value, "Compaction threshold", "flag data files under 128MB that should be compacted"),
    ]
    if run_health.value:
        _lines = [f"- **{name}** — would {desc} *(simulated — wire to live storage to run)*"
                  for on, name, desc in _checks if on]
        health_panel = ui.panel(mo,
            ui.header(mo, "Audit plan"),
            mo.md("\n".join(_lines) if _lines else "*No audits selected.*"),
        )
    else:
        health_panel = mo.md("*Toggle the audits and run to see the plan.*")
    return (health_panel,)


@app.cell(hide_code=True)
def _(docs_panel, health_compaction, health_crc, health_orphan, health_panel, health_schema, health_tombstone, mo, okf_panel, run_health, ui):
    tab_vault = mo.vstack([
        okf_panel,
        mo.hstack([docs_panel], gap=2),
        ui.panel(mo,
            ui.header(mo, "Data Health & Schema Validation"),
            mo.md("Select which audits to enforce on the storage and catalog paths:"),
            mo.hstack([
                mo.vstack([health_crc, health_schema]),
                mo.vstack([health_tombstone, health_orphan]),
                mo.vstack([health_compaction]),
            ], gap=3),
            mo.hstack([run_health]),
            health_panel,
        ),
    ])
    return (tab_vault,)


@app.cell(hide_code=True)
def _(
    cat,
    config_panel,
    deploy_btn,
    deployment_status,
    destroy_btn,
    inspect_output,
    logs,
    mo,
    ns_selector,
    save_btn,
    save_status,
    selector_panel,
    tab_metrics,
    tab_vault,
    table_selector,
    test_btn,
    test_input,
    test_output,
    ui,
    warnings_panel,
):
    tab_selection = mo.vstack([selector_panel, warnings_panel])

    tab_config = mo.vstack([config_panel, mo.hstack([save_btn, save_status])])

    tab_tester = mo.vstack([
        ui.panel(mo,
            ui.header(mo, "VRL Testing Console"),
            mo.md("Validate Vector transform rules before provisioning them in the container."),
        ),
        test_input,
        mo.hstack([test_btn]),
        test_output,
    ])

    tab_pulumi = mo.vstack([
        ui.panel(mo,
            ui.header(mo, "Infrastructure Lifecycle Manager"),
            mo.md("Spin up or tear down the selected MOAr stack locally in Docker via Pulumi."),
        ),
        mo.hstack([deploy_btn, destroy_btn]),
        deployment_status,
        mo.accordion({"Deployment Execution Logs":
                      mo.Html(f"<pre style='max-height:250px; overflow-y:auto;'>{''.join(logs)}</pre>")}),
    ])

    _inspector_selectors = (mo.hstack([ns_selector, table_selector])
                            if (cat and hasattr(ns_selector, "value")) else ns_selector)
    tab_inspector = mo.vstack([
        ui.panel(mo,
            ui.header(mo, "Iceberg Metadata Inspector"),
            mo.md("List tables and inspect schema/data from the active REST catalog."),
        ),
        _inspector_selectors,
        inspect_output,
    ])

    setup_tabs = mo.ui.tabs({
        "Component Selection": tab_selection,
        "Configuration": tab_config,
        "VRL Tester": tab_tester,
        "Strategy Vault & OKF": tab_vault,
    })
    manage_tabs = mo.ui.tabs({
        "Infrastructure": tab_pulumi,
        "Metadata Inspector": tab_inspector,
        "Observability": tab_metrics,
    })
    dashboard = mo.ui.tabs({"Setup": setup_tabs, "Manage": manage_tabs})
    dashboard
    return


if __name__ == "__main__":
    app.run()
