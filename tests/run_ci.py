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
        'test_personal_backup.PersonalBackup',
        'test_adguard_backup.AdGuardBackup',
        'test_audit_findings.AuditRecovery',
    ),
}


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
    args = parser.parse_args()
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
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(suites[args.suite]))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
