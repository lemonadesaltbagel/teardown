# Teardown runtime image (used by both the gate service and the clean workspace).
FROM docker:cli AS dockercli
FROM python:3.12-slim
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY pyproject.toml README.md LICENSE NOTICE /opt/teardown/
COPY docs/observer-playbook.md /opt/teardown/docs/
# the room files the wheel carries (pyproject force-include), named one by one: no local keys or build outputs
COPY deploy/Dockerfile deploy/Dockerfile.clean deploy/cleanroom.yaml deploy/observerroom.yaml deploy/compose.yaml \
     /opt/teardown/deploy/
COPY deploy/clean /opt/teardown/deploy/clean
COPY deploy/desktop-linux /opt/teardown/deploy/desktop-linux
COPY deploy/android-agent/AndroidManifest.xml deploy/android-agent/build.sh /opt/teardown/deploy/android-agent/
COPY deploy/android-agent/src /opt/teardown/deploy/android-agent/src
COPY src /opt/teardown/src
RUN pip install --no-cache-dir /opt/teardown
