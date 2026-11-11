"""Collect defining unittest classes once and preserve CI privilege contexts."""

import argparse
import importlib
import inspect
import os
from pathlib import Path
import sys
import unittest


SUITES = {
    'systemd': ('test_security_systemd.SecuritySystemd',),
    'nonroot': (
        'test_manager.Manager',
        'test_cover_sites.CoverResources',
        'test_release_asset.ReleaseAsset',
        'test_installer_compatibility.InstallerCompatibility',
        'test_ci_scope.CIScope',
        'test_recovery_extract.RecoveryExtract',
        'test_git_identity.GitIdentity',
        'test_integrated_features.IntegratedFeatures',
        'test_personal_xhttp.PersonalXHTTP',
        'test_amneziawg.AmneziaWG',
        'test_certificate_renewal.CertificateRenewal',
        'test_adguard.AdGuardInstaller',
        'test_audit_findings.AuditInstaller',
        'test_verified_release.VerifiedRelease',
    ),
    'integration': ('test_real_integration.RealIntegration',),
    'services': ('test_real_services.RealServices',),
    'root': (
        'test_domains.Domains',
        'test_manager.ManagerBackup',
        'test_cover_sites.CoverPublication',
        'test_audit_findings.DiagnosticsFiles',
        'test_personal_backup.PersonalBackup',
        'test_adguard_backup.AdGuardBackup',
        'test_audit_findings.AuditRecovery',
    ),
}


def root_shards(tests):
    """Partition root tests for parallel execution and a lock-exclusive phase."""
    shards = [[], [], [], [], []]
    personal_count = 0
    for case in tests:
        owner = type(case).__module__ + '.' + type(case).__name__
        if owner == 'test_personal_backup.PersonalBackup':
            shards[personal_count % 2].append(case)
            personal_count += 1
        elif owner == 'test_audit_findings.AuditRecovery':
            shards[2].append(case)
        elif owner == 'test_manager.ManagerBackup':
            # These tests launch recognizable legacy peers; keep them exclusive.
            shards[4].append(case)
        else:
            shards[3].append(case)
    assigned = [case.id() for shard in shards for case in shard]
    if not all(shards) or sorted(assigned) != sorted(case.id() for case in tests):
        raise ValueError('Root shards must cover every test exactly once')
    return shards


# Heavy gRPC fragmentation tests dominate the integration suite; each process
# below is balanced to run for roughly the same time as the others.
INTEGRATION_SHARD_1 = ('test_grpc_fragmented_full',)
INTEGRATION_SHARD_2 = (
    'test_grpc_fragmented_direct',
    'test_managed_hysteria_http3_and_disabled_roles',
    'test_amneziawg_tcp_udp_and_panel_restart',
    'test_vision_and_initial_client_official_api',
    'test_real_mihomo_generated_template',
    'test_telemt_backup_restore_accepts_real_manager_install_plan',
)


def integration_shards(tests):
    """Partition integration tests: two named groups and every other test in shard 3."""
    shards = [[], [], []]
    named = {name: index for index, names in enumerate((INTEGRATION_SHARD_1, INTEGRATION_SHARD_2))
             for name in names}
    method_names = {case.id().rsplit('.', 1)[1] for case in tests}
    missing = sorted(name for name in named if name not in method_names)
    if missing:
        raise ValueError('Integration shard names a missing test: ' + ', '.join(missing))
    for case in tests:
        shards[named.get(case.id().rsplit('.', 1)[1], 2)].append(case)
    assigned = [case.id() for shard in shards for case in shard]
    if not all(shards) or sorted(assigned) != sorted(case.id() for case in tests):
        raise ValueError('Integration shards must cover every test exactly once')
    return shards


def collect():
    directory = Path(__file__).resolve().parent
    sys.path.insert(0, str(directory))
    modules = sorted(directory.glob('test_*.py'))
    classes = {}
    for path in modules:
        module = importlib.import_module(path.stem)
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if issubclass(cls, unittest.TestCase) and cls.__module__ == module.__name__:
                classes[f'{module.__name__}.{cls.__qualname__}'] = cls

    assignments = {}
    for suite, names in SUITES.items():
        for name in names:
            if name in assignments:
                raise ValueError(f'Duplicate suite assignment: {name}')
            assignments[name] = suite
    unassigned = sorted(classes.keys() - assignments.keys())
    stale = sorted(assignments.keys() - classes.keys())
    if unassigned or stale:
        raise ValueError(f'Unassigned TestCase classes: {unassigned}; stale registry entries: {stale}')

    loader = unittest.TestLoader()
    suites = {name: [] for name in SUITES}
    test_ids = set()
    for name, cls in sorted(classes.items()):
        if not loader.getTestCaseNames(cls):
            raise ValueError(f'TestCase has no test methods: {name}')
        tests = list(loader.loadTestsFromTestCase(cls))
        for test in tests:
            if test.id() in test_ids:
                raise ValueError(f'Duplicate test ID: {test.id()}')
            test_ids.add(test.id())
        suites[assignments[name]].extend(tests)
    if loader.errors:
        raise ValueError('Test collection errors: ' + '\n'.join(loader.errors))
    for name, tests in suites.items():
        if not tests:
            raise ValueError(f'Empty suite: {name}')

    integration_shards(suites['integration'])

    print('CI TEST INVENTORY')
    print(f'Modules:          {len(modules)}')
    print(f'TestCase classes: {len(classes)}')
    print(f'Unique tests:     {len(test_ids)}')
    for name, tests in suites.items():
        print(f'{name}: {len(tests)}')
    print('COMPLETENESS: PASS', flush=True)
    return suites


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-completeness', action='store_true')
    mode.add_argument('--suite', choices=SUITES)
    parser.add_argument('--root-shard', type=int, choices=range(1, 6))
    parser.add_argument('--integration-shard', type=int, choices=range(1, 4))
    args = parser.parse_args()
    if args.root_shard is not None and args.suite != 'root':
        parser.error('--root-shard requires --suite root')
    if args.integration_shard is not None and args.suite != 'integration':
        parser.error('--integration-shard requires --suite integration')
    if args.suite and ((args.suite in ('root', 'systemd')) != (os.geteuid() == 0)):
        print(f'PRIVILEGE: FAIL — {args.suite} requires '
              + ('EUID 0' if args.suite in ('root', 'systemd') else 'EUID != 0'), file=sys.stderr)
        return 1
    try:
        suites = collect()
    except (Exception, SystemExit) as error:
        print(f'COMPLETENESS: FAIL — {error}', file=sys.stderr)
        return 1
    if args.check_completeness:
        return 0
    tests = suites[args.suite]
    if args.root_shard is not None:
        tests = root_shards(tests)[args.root_shard - 1]
        print(f'ROOT SHARD {args.root_shard}/5: {len(tests)} tests', flush=True)
    if args.integration_shard is not None:
        tests = integration_shards(tests)[args.integration_shard - 1]
        print(f'INTEGRATION SHARD {args.integration_shard}/3: {len(tests)} tests', flush=True)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(tests))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
