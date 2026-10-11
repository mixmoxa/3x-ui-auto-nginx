#!/usr/bin/env bash
# Run a real systemd guest using TCG; no KVM, privileges, host network or cgroups.
set -Eeuo pipefail
rm -f /work/reboot-policy.tar /work/pre-boot-id /work/expected-origins.json /work/reboot.cpio.gz
rm -rf /work/root
mkdir -p /work/root
tar -xf /work/rootfs.tar -C /work/root
cp -a /lib/modules /work/root/usr/lib/
mkdir /work/root/repo
cp -a /repo/. /work/root/repo/
rm -f /work/root/.dockerenv /work/root/etc/machine-id
if [[ -d /work/root/opt/xui-ci/apt ]]; then
    rm -f /work/root/etc/resolv.conf
    printf 'nameserver 8.8.8.8\nnameserver 8.8.4.4\n' > /work/root/etc/resolv.conf
    chmod 0644 /work/root/etc/resolv.conf
fi
mkdir -p /work/root/dev /work/root/proc /work/root/sys /work/root/run
cat > /work/root/init <<'INIT'
#!/bin/sh
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mount -t tmpfs tmpfs /run
exec /sbin/init
INIT
chmod 0755 /work/root/init
cat > /work/root/etc/systemd/system/xui-ci.service <<'UNIT'
[Unit]
After=systemd-journald.service dbus.service
[Service]
Type=oneshot
WorkingDirectory=/repo
ExecStart=/bin/bash -c 'python3 tests/run_ci.py --suite systemd; rc=$?; if [ "$rc" = 0 ]; then echo XUI_SYSTEMD_TEST_PASS; else echo XUI_SYSTEMD_TEST_FAIL; fi; systemctl poweroff; exit "$rc"'
StandardOutput=journal+console
StandardError=journal+console
[Install]
WantedBy=multi-user.target
UNIT
mkdir -p /work/root/etc/systemd/system/multi-user.target.wants
ln -sf ../xui-ci.service /work/root/etc/systemd/system/multi-user.target.wants/xui-ci.service
cd /work/root
find . -xdev -print0 | cpio --null -o --format=newc 2>/work/cpio.log | gzip -1 > /work/rootfs.cpio.gz
kernel=$(find /boot -maxdepth 1 -name 'vmlinuz-*' -type f | sort -V | tail -1)
[[ -n "$kernel" ]]
timeout 12m qemu-system-x86_64 -machine accel=tcg -m 2048 -smp 2 -nodefaults \
    -no-reboot -display none -serial stdio -monitor none -nic none \
    -fsdev local,id=ci,path=/work,security_model=none -device virtio-9p-pci,fsdev=ci,mount_tag=xui-ci \
    -kernel "$kernel" -initrd /work/rootfs.cpio.gz \
    -append 'console=ttyS0 panic=1 quiet rdinit=/init systemd.show_status=false' \
    | tee /work/systemd.log
grep -q 'XUI_SYSTEMD_TEST_PASS' /work/systemd.log
! grep -q 'XUI_SYSTEMD_TEST_FAIL' /work/systemd.log
[[ -f /work/reboot-policy.tar ]]
tar -xf /work/reboot-policy.tar -C /work/root
# This is the test-only Docker policy already explicitly removed in first boot.
rm -f /work/root/etc/apt/apt.conf.d/docker-disable-periodic-update
cat > /work/root/etc/systemd/system/xui-ci.service <<'UNIT'
[Unit]
After=systemd-journald.service dbus.service timers.target
[Service]
Type=oneshot
WorkingDirectory=/repo
Environment=PYTHONPATH=tests
ExecStart=/bin/bash -c 'python3 -c "from test_security_systemd import nightly_after_cold_boot; nightly_after_cold_boot()"; rc=$?; if [ "$rc" = 0 ]; then echo XUI_SECOND_BOOT_PASS; else echo XUI_SECOND_BOOT_FAIL; fi; systemctl poweroff; exit "$rc"'
StandardOutput=journal+console
StandardError=journal+console
[Install]
WantedBy=multi-user.target
UNIT
cd /work/root
find . -xdev -print0 | cpio --null -o --format=newc 2>/work/cpio-reboot.log | gzip -1 > /work/reboot.cpio.gz
timeout 4m qemu-system-x86_64 -machine accel=tcg -m 2048 -smp 2 -nodefaults \
    -no-reboot -display none -serial stdio -monitor none -nic none \
    -fsdev local,id=ci,path=/work,security_model=none -device virtio-9p-pci,fsdev=ci,mount_tag=xui-ci \
    -kernel "$kernel" -initrd /work/reboot.cpio.gz \
    -append 'console=ttyS0 panic=1 quiet rdinit=/init systemd.show_status=false' | tee /work/reboot.log
grep -q 'XUI_SECOND_BOOT_PASS' /work/reboot.log
! grep -q 'XUI_SECOND_BOOT_FAIL' /work/reboot.log
