ARG DISTRO=ubuntu:24.04
FROM ${DISTRO}
ENV DEBIAN_FRONTEND=noninteractive
RUN --mount=type=secret,id=proxy_ca,target=/run/proxy-ca.pem \
    if test -f /run/proxy-ca.pem; then printf 'Acquire::https::CaInfo "/run/proxy-ca.pem";\n' > /etc/apt/apt.conf.d/99test-proxy; fi; \
    apt-get update && apt-get install -y --no-install-recommends systemd systemd-sysv systemd-resolved dbus \
    openssh-server fail2ban unattended-upgrades nftables kmod nginx libnginx-mod-stream certbot sqlite3 \
    python3 python3-systemd python3-cryptography python3-configobj openssl ca-certificates iproute2 curl tcpdump tar gzip && \
    rm -f /etc/apt/apt.conf.d/99test-proxy && mkdir -p /run/sshd && ssh-keygen -A
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
