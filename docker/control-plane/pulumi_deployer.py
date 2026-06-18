import os
import yaml
import pulumi
import pulumi_docker as docker
from pulumi.automation import create_or_select_stack

def create_liger_program(config_dict):
    # Retrieve configuration variables
    storage_port = int(config_dict.get("components", {}).get("storage", {}).get("port", 8333))
    catalog_port = int(config_dict.get("components", {}).get("catalog", {}).get("port", 8181))
    vector_observe_port = int(config_dict.get("components", {}).get("pipeline", {}).get("observe_port", 8686))
    vector_ingest_port = int(config_dict.get("components", {}).get("pipeline", {}).get("ingest_port", 514))
    vrl_transform = config_dict.get("components", {}).get("pipeline", {}).get("vrl_transform", "")
    bucket_name = config_dict.get("components", {}).get("storage", {}).get("bucket_name", "liger-warehouse")

    # 1. Create a Docker Network
    network = docker.Network("liger-network", name="liger-network")
    
    # 2. PostgreSQL container (Polaris catalog metadata backend)
    postgres_db = docker.Container("postgres-db",
        name="postgres-db",
        image="postgres:15-alpine",
        networks_advanced=[docker.ContainerNetworksAdvancedArgs(name=network.name)],
        envs=[
            "POSTGRES_DB=polaris_catalog",
            "POSTGRES_USER=polaris",
            "POSTGRES_PASSWORD=polaris_pass"
        ],
        ports=[docker.ContainerPortArgs(internal=5432, external=5432)],
        restart="unless-stopped"
    )
    
    # 3. SeaweedFS container (S3-compatible object storage)
    seaweed = docker.Container("seaweedfs",
        name="seaweedfs",
        image="chrislusf/seaweedfs:latest",
        command=["server", "-s3", f"-s3.port={storage_port}"],
        networks_advanced=[docker.ContainerNetworksAdvancedArgs(name=network.name)],
        ports=[
            docker.ContainerPortArgs(internal=8333, external=storage_port),
            docker.ContainerPortArgs(internal=9333, external=9333)
        ],
        restart="unless-stopped"
    )
    
    # 4. Apache Polaris container (Iceberg REST catalog)
    polaris = docker.Container("polaris",
        name="polaris",
        image="apache/polaris:1.4.1", # Pinned secure release
        networks_advanced=[docker.ContainerNetworksAdvancedArgs(name=network.name)],
        envs=[
            "POLARIS_DATABASE_URL=jdbc:postgresql://postgres-db:5432/polaris_catalog",
            "POLARIS_DATABASE_USER=polaris",
            "POLARIS_DATABASE_PASSWORD=polaris_pass",
            "POLARIS_DEFAULT_AWS_KEY=aws_access_key",
            "POLARIS_DEFAULT_AWS_SECRET=aws_secret_key"
        ],
        ports=[docker.ContainerPortArgs(internal=8181, external=catalog_port)],
        opts=pulumi.ResourceOptions(depends_on=[postgres_db]),
        restart="unless-stopped"
    )
    
    # 5. Dynamic Vector Config File Preparation
    vector_config_content = f"""
sources:
  in_syslog:
    type: syslog
    address: 0.0.0.0:{vector_ingest_port}
    mode: tcp

transforms:
  process_logs:
    type: remap
    inputs: ["in_syslog"]
    source: |
{vrl_transform}

sinks:
  out_iceberg:
    type: aws_s3
    inputs: ["process_logs"]
    bucket: {bucket_name}
    endpoint: http://seaweedfs:{storage_port}
    key_prefix: OCSF/
    compression: gzip
    encoding:
      codec: json
    auth:
      access_key_id: aws_access_key
      secret_access_key: aws_secret_key
"""
    # Write config file locally so Docker can mount it
    config_dir = os.path.abspath("./temp_config")
    os.makedirs(config_dir, exist_ok=True)
    config_file_path = os.path.join(config_dir, "vector.yaml")
    with open(config_file_path, "w") as f:
        f.write(vector_config_content.strip())

    # 6. Vector container
    vector = docker.Container("vector",
        name="vector",
        image="vectordotdev/vector:0.36.0-alpine",
        command=["--config", "/etc/vector/vector.yaml"],
        networks_advanced=[docker.ContainerNetworksAdvancedArgs(name=network.name)],
        mounts=[docker.ContainerMountArgs(
            type="bind",
            source=config_file_path,
            target="/etc/vector/vector.yaml"
        )],
        ports=[
            docker.ContainerPortArgs(internal=vector_ingest_port, external=vector_ingest_port),
            docker.ContainerPortArgs(internal=8686, external=vector_observe_port)
        ],
        opts=pulumi.ResourceOptions(depends_on=[seaweed, polaris]),
        restart="unless-stopped"
    )

    # Exports
    pulumi.export("storage_endpoint", f"http://localhost:{storage_port}")
    pulumi.export("catalog_endpoint", f"http://localhost:{catalog_port}")
    pulumi.export("vector_observe", f"http://localhost:{vector_observe_port}")

def deploy_stack(config_dict, log_callback=None):
    project_name = "liger_control_plane"
    stack_name = "dev"

    def program():
        create_liger_program(config_dict)

    stack = create_or_select_stack(
        stack_name=stack_name,
        project_name=project_name,
        program=program
    )
    
    # Run the deployment
    up_result = stack.up(on_output=log_callback)
    return up_result.outputs

def destroy_stack(config_dict, log_callback=None):
    project_name = "liger_control_plane"
    stack_name = "dev"

    def program():
        create_liger_program(config_dict)

    stack = create_or_select_stack(
        stack_name=stack_name,
        project_name=project_name,
        program=program
    )
    
    # Run destruction
    destroy_result = stack.destroy(on_output=log_callback)
    return destroy_result
