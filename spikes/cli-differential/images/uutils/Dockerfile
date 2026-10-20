# uutils coreutils (Rust) release binary on the same base as the GNU image,
# so libc/locale/base files are identical and only the coreutils differ.
FROM debian:stable-slim
ADD uu.tgz /opt/
RUN set -e; d=$(ls -d /opt/coreutils-*); mkdir -p /opt/uu/bin; \
    mv "$d/coreutils" /opt/uu/coreutils; rm -rf "$d"; \
    for u in $(/opt/uu/coreutils --list); do ln -s ../coreutils /opt/uu/bin/$u; done
ENV PATH=/opt/uu/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
