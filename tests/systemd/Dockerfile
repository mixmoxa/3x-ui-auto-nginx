ARG DISTRO=ubuntu:24.04
FROM ${DISTRO}
ARG MINIMAL_DNS=0
ENV DEBIAN_FRONTEND=noninteractive
RUN --mount=type=secret,id=proxy_ca,target=/run/proxy-ca.pem \
    if test -f /run/proxy-ca.pem; then printf 'Acquire::https::CaInfo "/run/proxy-ca.pem";\n' > /etc/apt/apt.conf.d/99test-proxy; fi; \
    apt-get update && apt-get install -y --no-install-recommends systemd systemd-sysv systemd-resolved dbus \
    openssh-server fail2ban unattended-upgrades nftables kmod nginx libnginx-mod-stream certbot sqlite3 \
    python3 python3-systemd python3-cryptography python3-configobj openssl ca-certificates iproute2 curl wget jq procps iptables dpkg-dev tcpdump tar gzip && \
    rm -f /etc/apt/apt.conf.d/99test-proxy && mkdir -p /run/sshd && ssh-keygen -A
RUN --mount=type=secret,id=proxy_ca,target=/run/proxy-ca.pem \
    mkdir -p /opt/xui-ci && \
    if test -f /run/proxy-ca.pem; then export CURL_CA_BUNDLE=/run/proxy-ca.pem; fi; \
    curl -fLsS --retry 3 --connect-timeout 15 --max-time 120 \
      https://github.com/AdguardTeam/AdGuardHome/releases/download/v0.107.79/AdGuardHome_linux_amd64.tar.gz -o /tmp/agh.tar.gz && \
    printf 'c48f4a43000665484c5ec28177de11a004759b620dae8f77b2aabefc9ef3687f  /tmp/agh.tar.gz\n' | sha256sum --check --status && \
    tar -xzf /tmp/agh.tar.gz -C /opt/xui-ci --strip-components=2 ./AdGuardHome/AdGuardHome && rm /tmp/agh.tar.gz
RUN --mount=type=secret,id=proxy_ca,target=/run/proxy-ca.pem \
    if test "$MINIMAL_DNS" = 1; then \
      if test -f /run/proxy-ca.pem; then printf 'Acquire::https::CaInfo "/run/proxy-ca.pem";\n' > /etc/apt/apt.conf.d/99test-proxy; fi; \
      mkdir -p /opt/xui-ci/apt && cd /opt/xui-ci/apt && apt-get download systemd-resolved ufw && \
      for spec in xui-ci-upgrade:1 xui-ci-upgrade:2 xui-ci-retained:1; do \
        package=${spec%:*}; version=${spec#*:}; mkdir -p /tmp/ci-package/DEBIAN; \
        printf 'Package: %s\nVersion: %s\nArchitecture: all\nMaintainer: CI <ci@example.invalid>\nDescription: isolated APT regression fixture\n' "$package" "$version" > /tmp/ci-package/DEBIAN/control; \
        if test "$package:$version" = xui-ci-upgrade:2; then printf '#!/bin/sh\nset -e\ntouch /run/reboot-required\n' > /tmp/ci-package/DEBIAN/postinst; chmod 755 /tmp/ci-package/DEBIAN/postinst; fi; \
        dpkg-deb --build /tmp/ci-package "$package-$version.deb" && rm -rf /tmp/ci-package || exit 1; \
      done && dpkg-scanpackages --multiversion . > Packages && \
      dpkg -r systemd-resolved && rm -f /etc/apt/apt.conf.d/99test-proxy; \
    fi
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
