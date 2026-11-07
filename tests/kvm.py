"""Fail closed before a VM run; creating a VM proves usable KVM, not just a node."""
import fcntl
import json
import os
from pathlib import Path


def preflight():
    cpus = len(os.sched_getaffinity(0))
    if cpus < 4:
        raise RuntimeError('VM acceptance requires at least four available CPUs')
    try:
        with open('/dev/kvm', 'r+b') as device:
            version = fcntl.ioctl(device, 0xAE00, 0)  # KVM_GET_API_VERSION
            if version != 12:
                raise RuntimeError('Unsupported KVM API version')
            vm = fcntl.ioctl(device, 0xAE01, 0)  # KVM_CREATE_VM
            os.close(vm)
    except OSError as error:
        raise RuntimeError('KVM VM creation failed; no TCG fallback') from error
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    return dict(accelerator='kvm', kvm_api_version=version, available_cpus=cpus,
                host_memory_total_bytes=int(memory['MemTotal'].split()[0])*1024)


if __name__ == '__main__':
    print(json.dumps(preflight(), sort_keys=True), flush=True)
