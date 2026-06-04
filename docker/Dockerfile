# The reasoner toolchain for the OCSF-mapping gate, wrapped so nobody has to fight a JDK
# version to see the demo work: Java + ROBOT + Python3, and that is the whole interaction.
FROM eclipse-temurin:17-jre-jammy

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# ROBOT runs the ELK reasoner. Pin the version so the demo is reproducible.
ARG ROBOT_VERSION=1.9.6
RUN curl -fL -o /opt/robot.jar \
    "https://github.com/ontodev/robot/releases/download/v${ROBOT_VERSION}/robot.jar"
ENV ROBOT_JAR=/opt/robot.jar

WORKDIR /work
