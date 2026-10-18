FROM ubuntu:26.04
ENV DEBIAN_FRONTEND=noninteractive
RUN --mount=type=secret,id=proxy_ca,target=/run/proxy-ca.pem \
    if test -f /run/proxy-ca.pem; then printf 'Acquire::https::CaInfo "/run/proxy-ca.pem";\n' > /etc/apt/apt.conf.d/99pilot-ca; fi; \
    apt-get update && apt-get install -y --no-install-recommends systemd systemd-sysv systemd-resolved udev dbus openssh-server iproute2 iptables kmod ca-certificates curl python3 && \
    rm -f /etc/apt/apt.conf.d/99pilot-ca /etc/apt/apt.conf.d/docker-disable-periodic-update /etc/machine-id
CMD ["/sbin/init"]
