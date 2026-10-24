# Linux desktop target runtime: Xvfb + D-Bus + AT-SPI + GTK, with Teardown's in-container desktop agent.
FROM debian:stable-slim
RUN apt-get -o Acquire::Retries=10 -o Acquire::http::Timeout=900 update && apt-get -o Acquire::Retries=10 -o Acquire::http::Timeout=900 install -y --no-install-recommends \
      xvfb dbus-x11 at-spi2-core python3 python3-gi gir1.2-gtk-3.0 gir1.2-atspi-2.0 \
      fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
ENV NO_AT_BRIDGE=0 GTK_A11Y=atspi GDK_BACKEND=x11 LANG=C.UTF-8 TZ=UTC
COPY desktop_agent.py /opt/teardown/desktop_agent.py
RUN useradd -m -u 1000 app
USER app
WORKDIR /home/app
ENTRYPOINT ["python3", "-u", "/opt/teardown/desktop_agent.py"]
