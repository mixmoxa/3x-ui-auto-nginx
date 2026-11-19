ARG DISTRO=ubuntu:26.04
FROM ${DISTRO}
ENV DEBIAN_FRONTEND=noninteractive
RUN --mount=type=secret,id=proxy_ca,target=/run/proxy-ca.pem \
    --mount=type=bind,source=tests/ci_retry.sh,target=/tmp/ci_retry.sh \
    . /tmp/ci_retry.sh && \
    if test -f /run/proxy-ca.pem; then printf 'Acquire::https::CaInfo "/run/proxy-ca.pem";\n' > /etc/apt/apt.conf.d/99pilot-ca; fi && \
    ci_retry ci_apt_install apt-get systemd systemd-sysv systemd-resolved udev dbus openssh-server iproute2 iptables kmod ca-certificates curl python3 python3-aioquic && \
    rm -f /etc/apt/apt.conf.d/99pilot-ca /etc/apt/apt.conf.d/docker-disable-periodic-update /etc/machine-id
CMD ["/sbin/init"]
