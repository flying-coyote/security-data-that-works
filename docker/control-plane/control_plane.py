import marimo

__generated_with = "0.23.10"
app = marimo.App(width="medium")


@app.cell(hide_code=True)
def _():
    import marimo as mo
    import yaml
    import os
    import subprocess
    import sys
    import boto3
    try:
        from pyiceberg.catalog.rest import RestCatalog
    except ImportError:
        RestCatalog = None

    import sys
    sys.path.append(os.path.abspath("."))
    import pulumi_deployer as deployer

    PROVIDER_NAMES = {
        "seaweedfs": "SeaweedFS",
        "minio": "MinIO",
        "polaris": "Polaris",
        "nessie": "Nessie",
        "vector": "Vector",
        "fluentbit": "Fluent Bit"
    }

    return PROVIDER_NAMES, boto3, deployer, mo, os, subprocess, yaml, RestCatalog


@app.cell(hide_code=True)
def _(mo):
    branding_styles = mo.Html("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&family=JetBrains+Mono:ital,wght@0,100..800;1,100..800&display=swap');

:root {
  --color-teal-400: #5c8dc5;
  --color-teal-500: #4577b0;
  --color-teal-600: #36608f;
  --color-orange-300: #ad9e90;
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
    --color-orange-500: #ad9e90;
  }
}

.marimo-app {
  background-color: var(--color-bg-primary) !important;
  color: var(--color-text-primary) !important;
  font-family: var(--font-sans) !important;
}

h1, h2, h3, h4, h5, h6 {
  color: var(--color-text-display) !important;
  font-family: var(--font-sans) !important;
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

button.marimo-button, .marimo-button button {
  font-family: var(--font-sans) !important;
  font-weight: 500 !important;
  border-radius: 0px !important;
  border: 1px solid var(--color-border-subtle) !important;
  background-color: var(--color-bg-subtle) !important;
  color: var(--color-text-primary) !important;
  transition: all 150ms ease !important;
  padding: 0.5rem 1rem !important;
}

button.marimo-button:hover, .marimo-button button:hover {
  background-color: var(--color-teal-50) !important;
  border-color: var(--color-teal-400) !important;
  color: var(--color-teal-600) !important;
}

.sdw-card {
  background-color: var(--color-bg-primary) !important;
  border: 1px solid var(--color-border-subtle) !important;
  padding: 1.5rem;
  border-radius: 0px !important;
  margin-bottom: 1.5rem;
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

.sdw-title span.works {
  color: var(--color-teal-400);
}
</style>
""")
    # Render full branded header lockup
    header_lockup = mo.Html("""
<div class="sdw-header">
    <svg width="40" height="40" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
        <!-- Row 1 -->
        <rect x="5" y="5" width="26" height="26" fill="#c14a4a" />
        <rect x="37" y="5" width="26" height="26" fill="#d6824a" />
        <rect x="69" y="5" width="26" height="26" fill="#d6b94a" />
        <!-- Row 2 -->
        <rect x="5" y="37" width="26" height="26" fill="#d6b94a" />
        <rect x="37" y="37" width="26" height="26" fill="#6f9a4f" />
        <rect x="69" y="37" width="26" height="26" fill="#36608f" />
        <!-- Row 3 -->
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
        ### LIGER Stack Control Plane
        Reactive administrator cockpit for the Modular Open Architecture Security-Data (MOAR) Liger Stack.
        """)
    ])
    return


@app.cell(hide_code=True)
def _(os, yaml):
    # Load configuration
    config_path = "liger-spec.yaml"
    if not os.path.exists(config_path):
        config_data = {}
    else:
        with open(config_path, "r") as _f:
            config_data = yaml.safe_load(_f) or {}
    return config_data, config_path


@app.cell(hide_code=True)
def _(config_data, mo):
    # Normalize pipeline values to labels
    saved_pipeline = config_data.get("components", {}).get("pipeline", {}).get("provider", ["vector"])
    if isinstance(saved_pipeline, str):
        saved_pipeline = [saved_pipeline]
    pipeline_labels = []
    for p in saved_pipeline:
        if p == "vector":
            pipeline_labels.append("Vector")
        elif p == "fluentbit":
            pipeline_labels.append("Fluent Bit")

    saved_storage = config_data.get("components", {}).get("storage", {}).get("provider", "seaweedfs")
    storage_label = "SeaweedFS" if saved_storage == "seaweedfs" else "MinIO"

    saved_catalog = config_data.get("components", {}).get("catalog", {}).get("provider", "polaris")
    catalog_label = "Polaris" if saved_catalog == "polaris" else "Nessie"

    storage_provider = mo.ui.radio(
        options=["SeaweedFS", "MinIO"], 
        value=storage_label, 
        label="Storage Provider",
        inline=True
    )
    catalog_provider = mo.ui.radio(
        options=["Polaris", "Nessie"], 
        value=catalog_label, 
        label="Catalog Provider",
        inline=True
    )
    pipeline_provider = mo.ui.multiselect(
        options=["Vector", "Fluent Bit"], 
        value=pipeline_labels, 
        label="Pipeline Engine(s)"
    )
    return storage_provider, catalog_provider, pipeline_provider


@app.cell(hide_code=True)
def _(storage_provider, catalog_provider, pipeline_provider, mo):
    selector_panel = mo.vstack([
        mo.md("### 🔌 Modular Component Selection"),
        mo.md("Choose the software components for your active LIGER stack deployment."),
        mo.hstack([storage_provider, catalog_provider, pipeline_provider])
    ]).style({
        "border": "1px solid var(--color-border-subtle)",
        "padding": "1.5rem",
        "background-color": "var(--color-bg-primary)",
        "margin-bottom": "1.5rem"
    })
    return (selector_panel,)


@app.cell(hide_code=True)
def _(config_data, storage_provider, catalog_provider, pipeline_provider, PROVIDER_NAMES, mo):
    # Dynamic settings based on selectors
    # Convert labels back to lowercase codes
    s_prov = storage_provider.value.lower() if storage_provider.value else "seaweedfs"
    s_name = PROVIDER_NAMES.get(s_prov, s_prov)
    default_s_port = 8333 if s_prov == "seaweedfs" else 9000
    storage_port = mo.ui.text(value=str(config_data.get("components", {}).get("storage", {}).get("port", default_s_port)), label=f"{s_name} Port")
    storage_bucket = mo.ui.text(value=config_data.get("components", {}).get("storage", {}).get("bucket_name", "liger-warehouse"), label="S3 Bucket Name")

    # 2. Catalog config
    c_prov = catalog_provider.value.lower() if catalog_provider.value else "polaris"
    c_name = PROVIDER_NAMES.get(c_prov, c_prov)
    default_c_port = 8181 if c_prov == "polaris" else 19120
    catalog_port = mo.ui.text(value=str(config_data.get("components", {}).get("catalog", {}).get("port", default_c_port)), label=f"{c_name} Port")

    # 3. Pipeline config (Define both Vector and Fluent Bit configuration widgets)
    vector_ingest_port = mo.ui.text(value=str(config_data.get("components", {}).get("pipeline", {}).get("ingest_port", 514)), label="Vector Ingest Port (Syslog TCP)")
    vector_observe_port = mo.ui.text(value=str(config_data.get("components", {}).get("pipeline", {}).get("observe_port", 8686)), label="Vector Observability Port")
    vrl_transform = mo.ui.text_area(value=config_data.get("components", {}).get("pipeline", {}).get("vrl_transform", ""), label="Vector VRL Transform Rule", rows=12)

    fluentbit_ingest_port = mo.ui.text(value=str(config_data.get("components", {}).get("pipeline", {}).get("fluentbit_ingest_port", 24224)), label="Fluent Bit Ingest Port")
    fluentbit_observe_port = mo.ui.text(value=str(config_data.get("components", {}).get("pipeline", {}).get("fluentbit_observe_port", 2020)), label="Fluent Bit Monitor Port")
    fluentbit_transform = mo.ui.text_area(value=config_data.get("components", {}).get("pipeline", {}).get("fluentbit_transform", ""), label="Fluent Bit Parsers Rule", rows=12)

    return (
        storage_port,
        storage_bucket,
        catalog_port,
        vector_ingest_port,
        vector_observe_port,
        vrl_transform,
        fluentbit_ingest_port,
        fluentbit_observe_port,
        fluentbit_transform,
    )


@app.cell(hide_code=True)
def _(
    storage_port,
    storage_bucket,
    catalog_port,
    vector_ingest_port,
    vector_observe_port,
    vrl_transform,
    fluentbit_ingest_port,
    fluentbit_observe_port,
    fluentbit_transform,
    storage_provider,
    catalog_provider,
    pipeline_provider,
    mo,
):
    s_prov = storage_provider.value.lower() if storage_provider.value else "storage"
    s_name = "SeaweedFS" if s_prov == "seaweedfs" else "MinIO"
    storage_settings = mo.vstack([
        mo.md(f"### 📁 {s_name} Settings"),
        mo.hstack([storage_port, storage_bucket])
    ]).style({
        "border": "1px solid var(--color-border-subtle)",
        "padding": "1.5rem",
        "background-color": "var(--color-bg-primary)",
        "margin-bottom": "1.5rem"
    })

    c_prov = catalog_provider.value.lower() if catalog_provider.value else "catalog"
    c_name = "Polaris" if c_prov == "polaris" else "Nessie"
    catalog_settings = mo.vstack([
        mo.md(f"### 🗂️ {c_name} Settings"),
        catalog_port
    ]).style({
        "border": "1px solid var(--color-border-subtle)",
        "padding": "1.5rem",
        "background-color": "var(--color-bg-primary)",
        "margin-bottom": "1.5rem"
    })

    p_provs = [p.lower().replace(" ", "") for p in (pipeline_provider.value or [])]
    pipeline_settings = []
    
    if "vector" in p_provs:
        pipeline_settings.append(
            mo.vstack([
                mo.md("### ⚡ Vector Settings"),
                mo.hstack([vector_ingest_port, vector_observe_port]),
                vrl_transform
            ]).style({
                "border": "1px solid var(--color-border-subtle)",
                "padding": "1.5rem",
                "background-color": "var(--color-bg-primary)",
                "margin-bottom": "1.5rem"
            })
        )
        
    if "fluentbit" in p_provs:
        pipeline_settings.append(
            mo.vstack([
                mo.md("### ⚡ Fluent Bit Settings"),
                mo.hstack([fluentbit_ingest_port, fluentbit_observe_port]),
                fluentbit_transform
            ]).style({
                "border": "1px solid var(--color-border-subtle)",
                "padding": "1.5rem",
                "background-color": "var(--color-bg-primary)",
                "margin-bottom": "1.5rem"
            })
        )

    config_panel = mo.vstack([
        storage_settings,
        catalog_settings,
        mo.vstack(pipeline_settings) if pipeline_settings else mo.md("⚠️ *Select at least one Pipeline Engine to configure.*")
    ])
    return (config_panel,)


@app.cell(hide_code=True)
def _(mo):
    save_btn = mo.ui.button(label="💾 Save Configuration Specs", kind="success")
    return (save_btn,)


@app.cell(hide_code=True)
def _(
    storage_provider,
    catalog_provider,
    pipeline_provider,
    storage_port,
    storage_bucket,
    catalog_port,
    vector_ingest_port,
    vector_observe_port,
    vrl_transform,
    fluentbit_ingest_port,
    fluentbit_observe_port,
    fluentbit_transform,
    config_path,
    save_btn,
    mo,
    yaml
):
    save_status = mo.md("*Save configuration before deploying.*")
    if save_btn.value:
        s_val = storage_provider.value.lower() if storage_provider.value else "seaweedfs"
        c_val = catalog_provider.value.lower() if catalog_provider.value else "polaris"
        p_vals = [p.lower().replace(" ", "") for p in (pipeline_provider.value or [])]
        
        updated_config = {
            "version": "1.0.0",
            "components": {
                "storage": {
                    "provider": s_val,
                    "bucket_name": storage_bucket.value,
                    "port": int(storage_port.value),
                    "volume_size_gb": 10
                },
                "catalog": {
                    "provider": c_val,
                    "port": int(catalog_port.value),
                    "admin_client_id": "admin",
                    "admin_client_secret": "adminsecret"
                },
                "pipeline": {
                    "provider": p_vals,
                    "observe_port": int(vector_observe_port.value),
                    "ingest_port": int(vector_ingest_port.value),
                    "vrl_transform": vrl_transform.value,
                    "fluentbit_observe_port": int(fluentbit_observe_port.value),
                    "fluentbit_ingest_port": int(fluentbit_ingest_port.value),
                    "fluentbit_transform": fluentbit_transform.value
                }
            }
        }
        with open(config_path, "w") as _f:
            yaml.safe_dump(updated_config, _f)
        save_status = mo.md("✅ **liger-spec.yaml updated!**")
    return (save_status,)


@app.cell(hide_code=True)
def _(mo):
    test_input = mo.ui.text_area(value='{"message": "log line", "timestamp": "2026-06-18T12:00:00Z", "user": "admin", "success": true}', label="Sample JSON Record In", rows=4)
    test_btn = mo.ui.button(label="🧪 Run Pre-Deployment VRL Test", kind="success")
    return test_btn, test_input


@app.cell(hide_code=True)
def _(mo, os, subprocess, test_btn, test_input, vrl_transform):
    test_output = ""
    if test_btn.value:
        indented_vrl = "\n".join("      " + line for line in vrl_transform.value.splitlines())
        temp_config = f"""
sources:
  test_src:
    type: stdin

transforms:
  test_vrl:
    type: remap
    inputs: ["test_src"]
    source: |
{indented_vrl}

sinks:
  test_sink:
    type: console
    inputs: ["test_vrl"]
    encoding:
      codec: json
"""
        temp_file = "temp_test_config.yaml"
        with open(temp_file, "w") as _tf:
            _tf.write(temp_config)

        try:
            res = subprocess.run(
                ["vector", "test", "--config", temp_file],
                input=test_input.value,
                capture_output=True,
                text=True
            )
            os.remove(temp_file)
            test_output = mo.md(f"**VRL Test Run Output:**\n```json\n{res.stdout or res.stderr}\n```")
        except Exception as e:
            test_output = mo.md(f"⚠️ **VRL Test Error:** Vector binary not found or failed: {str(e)}")

    return (test_output,)


@app.cell(hide_code=True)
def _(mo):
    deploy_btn = mo.ui.button(label="🚀 Deploy Stack via Pulumi", kind="success")
    destroy_btn = mo.ui.button(label="🛑 Tear Down Stack", kind="danger")
    return deploy_btn, destroy_btn


@app.cell(hide_code=True)
def _(config_path, deploy_btn, deployer, destroy_btn, mo, yaml):
    logs = []
    def log_callback(message):
        logs.append(message)

    deployment_status = mo.md("*Deployer Idle.*")

    if deploy_btn.value:
        with open(config_path, "r") as _f:
            current_config = yaml.safe_load(_f) or {}
        try:
            outputs = deployer.deploy_stack(current_config, log_callback=log_callback)
            deployment_status = mo.md(f"✅ **Stack successfully deployed!**\nEndpoints:\n- S3 Storage: {outputs.get('storage_endpoint').value}\n- Catalog URL: {outputs.get('catalog_endpoint').value}\n- Observability Dashboard: {outputs.get('vector_observe').value}")
        except Exception as e:
            deployment_status = mo.md(f"❌ **Deployment Failed:** {str(e)}")

    elif destroy_btn.value:
        with open(config_path, "r") as _f:
            current_config = yaml.safe_load(_f) or {}
        try:
            deployer.destroy_stack(current_config, log_callback=log_callback)
            deployment_status = mo.md("✅ **Stack destroyed.**")
        except Exception as e:
            deployment_status = mo.md(f"❌ **Stack destruction failed:** {str(e)}")
    return deployment_status, logs


@app.cell(hide_code=True)
def _(RestCatalog, catalog_port, storage_port, catalog_provider):
    cat = None
    catalog_error = None
    if RestCatalog and catalog_provider.value == "polaris" and catalog_port.value and storage_port.value:
        try:
            # Connect via RestCatalog
            cat = RestCatalog(
                "liger_catalog",
                **{
                    "type": "rest",
                    "uri": f"http://localhost:{catalog_port.value}",
                    "warehouse": "liger-warehouse",
                    "s3.endpoint": f"http://localhost:{storage_port.value}",
                    "s3.access-key-id": "aws_access_key",
                    "s3.secret-access-key": "aws_secret_key",
                    "s3.path-style-access": "true",
                    "s3.region": "us-east-1",
                }
            )
        except Exception as e:
            catalog_error = str(e)
    return cat, catalog_error


@app.cell(hide_code=True)
def _(cat, mo, catalog_error):
    namespaces = []
    ns_selector = None
    if cat is None:
        if catalog_error:
            ns_selector = mo.md(f"⚠️ **REST Catalog Connection Error**: `{catalog_error}`. Deploy stack first.")
        else:
            ns_selector = mo.md("ℹ️ *REST Catalog is currently offline or unconfigured. Deploy stack to query.*")
    else:
        try:
            namespaces = cat.list_namespaces()
            if namespaces:
                ns_names = [".".join(ns) if isinstance(ns, (list, tuple)) else str(ns) for ns in namespaces]
                ns_selector = mo.ui.dropdown(options=ns_names, value=ns_names[0], label="Select Namespace")
            else:
                ns_selector = mo.md("*No namespaces found. Please write data first.*")
        except Exception as e:
            ns_selector = mo.md(f"⚠️ **Failed to list namespaces**: `{str(e)}`")
    return namespaces, ns_selector


@app.cell(hide_code=True)
def _(cat, ns_selector, mo):
    table_selector = None
    if cat and ns_selector and hasattr(ns_selector, "value") and isinstance(ns_selector.value, str):
        try:
            ns_tuple = tuple(ns_selector.value.split("."))
            tables = cat.list_tables(ns_tuple)
            if tables:
                t_names = [".".join(t[1:]) if len(t) > 1 else str(t[0]) for t in tables]
                table_selector = mo.ui.dropdown(options=t_names, value=t_names[0], label="Select Iceberg Table")
            else:
                table_selector = mo.md("*No tables found in this namespace.*")
        except Exception as e:
            table_selector = mo.md(f"⚠️ **Failed to list tables**: `{str(e)}`")
    return table_selector


@app.cell(hide_code=True)
def _(cat, ns_selector, table_selector, mo):
    inspect_output = ""
    if cat and ns_selector and hasattr(ns_selector, "value") and isinstance(ns_selector.value, str) and table_selector and hasattr(table_selector, "value") and isinstance(table_selector.value, str):
        try:
            tbl_identifier = f"{ns_selector.value}.{table_selector.value}"
            table = cat.load_table(tbl_identifier)
            schema = table.schema()
            
            # Formatted columns list
            columns_data = []
            for field in schema.fields:
                columns_data.append({
                    "Field Name": field.name,
                    "Type": str(field.field_type),
                    "Required": "Yes" if field.required else "No"
                })
            
            import pandas as pd
            schema_df = pd.DataFrame(columns_data)
            
            # Load preview data
            try:
                arrow_table = table.scan().to_arrow()
                total_rows = arrow_table.num_rows
                preview_df = arrow_table.to_pandas().tail(10)
                preview_html = mo.as_html(preview_df)
            except Exception as scan_err:
                total_rows = 0
                preview_html = mo.md(f"*No records ingested yet or failed to scan: {str(scan_err)}*")
                
            inspect_output = mo.vstack([
                mo.md(f"#### Table: `{tbl_identifier}` (Total Rows: {total_rows})"),
                mo.md("##### 📐 Schema definition:"),
                mo.as_html(schema_df),
                mo.md("##### 📋 Last 10 Records Preview:"),
                preview_html
            ])
        except Exception as e:
            inspect_output = mo.md(f"⚠️ Failed to load table metadata: {str(e)}")
    else:
        inspect_output = mo.md("*Select a catalog namespace and table to inspect.*")
    return (inspect_output,)


@app.cell(hide_code=True)
def _(
    selector_panel,
    config_panel,
    save_btn,
    save_status,
    test_input,
    test_btn,
    test_output,
    deploy_btn,
    destroy_btn,
    deployment_status,
    logs,
    inspect_output,
    ns_selector,
    table_selector,
    cat,
    mo
):
    # Tab 1: Modular Component Selection
    tab_selection = selector_panel
    
    # Tab 2: Config Settings
    tab_config = mo.vstack([
        config_panel,
        mo.hstack([save_btn, save_status])
    ])
    
    # Tab 3: VRL Tester
    tab_tester = mo.vstack([
        mo.vstack([
            mo.md("### 🧪 VRL Testing Console"),
            mo.md("Test your vector transform rules against raw mock logs locally before provisioning them in the docker vector container.")
        ]).style({
            "border": "1px solid var(--color-border-subtle)",
            "padding": "1.5rem",
            "background-color": "var(--color-bg-primary)",
            "margin-bottom": "1.5rem"
        }),
        test_input,
        mo.hstack([test_btn]),
        test_output
    ])
    
    # Tab 4: Infrastructure
    tab_pulumi = mo.vstack([
        mo.vstack([
            mo.md("### 🛠️ Infrastructure Lifecycle Manager"),
            mo.md("Spin up or tear down your selected LIGER stack components locally inside docker container networks using Pulumi.")
        ]).style({
            "border": "1px solid var(--color-border-subtle)",
            "padding": "1.5rem",
            "background-color": "var(--color-bg-primary)",
            "margin-bottom": "1.5rem"
        }),
        mo.hstack([deploy_btn, destroy_btn]),
        deployment_status,
        mo.accordion({"Deployment Execution Logs": mo.Html(f"<pre style='max-height: 250px; overflow-y: auto;'>{''.join(logs)}</pre>")})
    ])
    
    # Tab 5: Metadata Inspector
    inspector_selectors = mo.hstack([ns_selector, table_selector]) if (cat and hasattr(ns_selector, "value")) else ns_selector
    tab_inspector = mo.vstack([
        mo.vstack([
            mo.md("### 🔍 Iceberg Metadata Inspector"),
            mo.md("Query schemas, list tables, and inspect metadata/data from your active REST catalog.")
        ]).style({
            "border": "1px solid var(--color-border-subtle)",
            "padding": "1.5rem",
            "background-color": "var(--color-bg-primary)",
            "margin-bottom": "1.5rem"
        }),
        inspector_selectors,
        inspect_output
    ])
    
    # Combined dashboard with premium styling
    dashboard = mo.ui.tabs({
        "🔌 Component Selection": tab_selection,
        "⚙️ Configuration": tab_config,
        "🧪 VRL Tester": tab_tester,
        "🛠️ Infrastructure": tab_pulumi,
        "🔍 Metadata Inspector": tab_inspector
    })
    
    dashboard
    return (dashboard,)


if __name__ == "__main__":
    app.run()
