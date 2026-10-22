# Teardown runtime image (used by both the gate service and the clean workspace).
FROM docker:cli AS dockercli
FROM python:3.12-slim
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY pyproject.toml README.md LICENSE NOTICE /opt/teardown/
COPY docs/observer-playbook.md /opt/teardown/docs/
COPY src /opt/teardown/src
RUN pip install --no-cache-dir /opt/teardown
