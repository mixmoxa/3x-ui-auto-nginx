#!/bin/bash
set -Eeuo pipefail
umask 077
cd /pilot
rm -rf /pilot/root
mkdir root
# Exported Ubuntu minimal OS, no tested application packages.
tar -xf rootfs.tar -C root
cp -a /lib/modules root/usr/lib/
rm -f root/.dockerenv root/usr/sbin/policy-rc.d root/etc/apt/apt.conf.d/docker-gzip-indexes root/etc/apt/apt.conf.d/docker-clean root/etc/apt/apt.conf.d/docker-autoremove-suggests
printf "xui-fresh-pilot\n" > root/etc/hostname
printf "LANG=C.UTF-8\n" > root/etc/locale.conf
cat /proc/sys/kernel/random/uuid | tr -d -- "-" > root/etc/machine-id
printf "/dev/vda / ext4 defaults 0 1\n" > root/etc/fstab
mkdir -p root/root/pilot root/dev root/proc root/sys root/run root/etc/systemd/network root/etc/letsencrypt root/etc/ssh/sshd_config.d
cp /repo/x-ui-latest.sh root/root/pilot/
cp /repo/tests/fresh/install.py /repo/tests/fresh/checks.py root/root/pilot/
cp /repo/assets/amneziawg/managed.py root/root/pilot/session.py
cp /repo/assets/client/managed.py root/root/pilot/client.py
cp /repo/assets/security/managed.py root/root/pilot/current-security.py
cp old-security.py root/root/pilot/old-security.py
PYTHONPATH=/repo/tests python3 -c 'import json; from release_contract import baseline; b=baseline(); print(json.dumps({"version":b["version"],"xray":b["xray"]}))' > root/root/pilot/baseline.json
cp /run/proxy-ca.pem root/usr/local/share/ca-certificates/pilot-proxy.crt
openssl req -x509 -newkey rsa:2048 -nodes -days 3 -keyout fixture.key -out fixture.crt -subj /CN=pilot-fixture -addext 'subjectAltName=DNS:localhost,IP:10.0.2.2,DNS:one.one.one.one,DNS:dns.google,DNS:dns.cloudflare.com,DNS:dns.quad9.net,DNS:adguardteam.github.io' >/pilot/cert-prep.log 2>&1
cp fixture.crt fixture.key root/root/pilot/
cp fixture.crt root/usr/local/share/ca-certificates/pilot-fixture.crt
test -f ssh-key || ssh-keygen -t ed25519 -N '' -f ssh-key >/dev/null
rm -rf root/root/.ssh
mkdir -m700 root/root/.ssh
cp ssh-key.pub root/root/.ssh/authorized_keys
printf 'PermitRootLogin prohibit-password\n' > root/etc/ssh/sshd_config.d/99pilot.conf
cat > root/etc/systemd/network/10-pilot.network <<'EOF'
[Match]
Name=en*
[Network]
DHCP=no
Address=10.0.2.15/24
Gateway=10.0.2.2
DNS=10.0.2.2
Domains=tech0.ru
DNSDefaultRoute=yes
EOF
# Stable NIC name, normal networkd provider DNS and search domain.
sed -i 's/Name=en\*/Name=eth0/' root/etc/systemd/network/10-pilot.network
ln -sf /run/systemd/resolve/stub-resolv.conf root/etc/resolv.conf
for unit in systemd-networkd systemd-resolved ssh; do
 ln -sf /usr/lib/systemd/system/$unit.service root/etc/systemd/system/multi-user.target.wants/$unit.service
done
cat > root/root/pilot/external-network.sh <<'EOF'
#!/bin/bash
set -e
# Test external boundary only: do not assign real resolver IPs to the guest.
for ip in 1.1.1.1 1.0.0.1 8.8.8.8 8.8.4.4 9.9.9.9; do
    iptables -t nat -A OUTPUT -d "$ip" -p tcp --dport 853 -j DNAT --to-destination 10.0.2.2:853
    for protocol in tcp udp; do
        iptables -t nat -A OUTPUT -d "$ip" -p "$protocol" --dport 53 -j DNAT --to-destination 10.0.2.2:53
    done
done
EOF
cat > root/etc/systemd/system/pilot-external-network.service <<'EOF'
[Unit]
After=network.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash /root/pilot/external-network.sh
[Install]
WantedBy=multi-user.target
EOF
ln -sf ../pilot-external-network.service root/etc/systemd/system/multi-user.target.wants/pilot-external-network.service
cat > root/etc/letsencrypt/cli.ini <<'EOF'
server = https://10.0.2.2:14000/dir
EOF
# Preserve the execution environment's managed proxy; no values in public logs.
python3 - <<'PY'
import json,os,socket
from pathlib import Path
from urllib.parse import urlsplit
root=Path('root');env={k:v for k,v in os.environ.items() if k.lower() in ('http_proxy','https_proxy','all_proxy','no_proxy')}
env['XUI_AUTO_REF']=os.environ['XUI_AUTO_REF']
for k in ('no_proxy','NO_PROXY'):env[k]='localhost,127.0.0.1,10.0.2.2,.example.test'
(root/'root/pilot/environment.json').write_text(json.dumps(env))
with (root/'etc/hosts').open('a') as f:
 for k,v in env.items():
  if k.lower() in ('http_proxy','https_proxy','all_proxy'):
   host=urlsplit(v).hostname
   if host:f.write('\n'+socket.gethostbyname(host)+' '+host+'\n')
PY
# Normal OS configuration is readable by the unprivileged networkd/resolved services.
chmod 0755 root
chmod 0644 root/etc/hostname root/etc/locale.conf root/etc/machine-id root/etc/hosts root/etc/systemd/network/10-pilot.network root/usr/local/share/ca-certificates/*.crt
# Standard distro kernel initrd mounts a persistent disk; guest applications stay on disk.
kernel=$(find /boot -maxdepth 1 -name 'vmlinuz-*' -type f | sort -V | tail -1)
version=${kernel##*/vmlinuz-}
mkinitramfs -o /pilot/initrd.img "$version" > initrd-build.log 2>&1
truncate -s 12G clean.raw
mkfs.ext4 -q -F -d root clean.raw > disk-build.log 2>&1
printf '%s\n' "$kernel" > kernel.path
date -u +%s > preparation.end
