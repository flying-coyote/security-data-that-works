# The reasoner toolchain for the OCSF-mapping gate, wrapped so nobody has to fight a JDK
# version to see the demo work: Java + ROBOT + Python3, and that is the whole interaction.
FROM eclipse-temurin:17-jre-jammy

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# ROBOT runs the ELK reasoner. Pin the version and the jar's checksum so the demo is
# reproducible and a swapped download fails the build. The sha256 is of the v1.9.6 release
# asset, hashed 2026-11-17; change both lines together.
ARG ROBOT_VERSION=1.9.6
ARG ROBOT_SHA256=3d112f47a5c2e82fd96c2bc40e582a86d1e6ad24f67648ef103ec5f21985ba5e
RUN curl -fL -o /opt/robot.jar \
    "https://github.com/ontodev/robot/releases/download/v${ROBOT_VERSION}/robot.jar" \
    && echo "${ROBOT_SHA256}  /opt/robot.jar" | sha256sum -c -
ENV ROBOT_JAR=/opt/robot.jar

WORKDIR /work
