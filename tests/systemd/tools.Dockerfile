FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN --mount=type=secret,id=proxy_ca,target=/run/proxy-ca.pem \
    if test -f /run/proxy-ca.pem; then printf 'Acquire::https::CaInfo "/run/proxy-ca.pem";\n' > /etc/apt/apt.conf.d/99test-proxy; fi; \
    apt-get update && apt-get install -y --no-install-recommends linux-image-virtual qemu-system-x86 cpio python3 && \
    rm -f /etc/apt/apt.conf.d/99test-proxy
