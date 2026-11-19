FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN --mount=type=secret,id=proxy_ca,target=/run/proxy-ca.pem \
    --mount=type=bind,source=tests/ci_retry.sh,target=/tmp/ci_retry.sh \
    . /tmp/ci_retry.sh && \
    if test -f /run/proxy-ca.pem; then printf 'Acquire::https::CaInfo "/run/proxy-ca.pem";\n' > /etc/apt/apt.conf.d/99test-proxy; fi && \
    ci_retry ci_apt_install apt-get linux-image-virtual qemu-system-x86 cpio time python3 initramfs-tools busybox-static openssh-client curl openssl && \
    rm -f /etc/apt/apt.conf.d/99test-proxy
