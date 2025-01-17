#
# Copyright oVirt Authors
# SPDX-License-Identifier: GPL-2.0-or-later
#
#
from distutils.version import LooseVersion
from functools import cache
import os

import logging
import ovirtsdk4
import pytest

from testlib import address_family

SUITE = os.environ['SUITE']
SUITE_VERSION = SUITE.split('-')[-1]
LOGGER = logging.getLogger(__name__)


def suite_dir():
    return os.path.join(os.environ['OST_REPO_ROOT'], os.environ['SUITE'])


def playbook_dir():
    return os.path.join(suite_dir(), 'ansible')


@cache
def af():
    """
    The address family to use for all connections in the session.
    IP_VERSION environment variable expected values: '4' or '6'.
    """
    default_ip_version = '4'
    try:
        version = os.environ['IP_VERSION']
        if version not in ['4', '6']:
            LOGGER.warning(
                f'suite invoked with unsupported version '
                f'"{version}". using version {default_ip_version}'
            )
            version = default_ip_version
    except KeyError:
        version = default_ip_version
    return address_family.AF(version)


def xfail_suite_master(reason, raises=None):
    return pytest.mark.xfail(
        condition=SUITE.endswith('master'),
        reason=reason,
        raises=raises,
        run=False,
    )


def xfail_suite_43(reason):
    return pytest.mark.xfail(
        condition=SUITE.endswith('4.3'), reason=reason, run=False
    )


def skip_suites_below(version):
    skip = is_suite_below(version)
    return pytest.mark.skipif(
        skip, reason=_skip_reason(skip, 'suite version {}'.format(version))
    )


def is_suite_below(version):
    return _compare_versions(SUITE_VERSION, version) < 0


def skip_sdk_below(version):
    skip = _is_sdk_below(version)
    return pytest.mark.skipif(
        skip, reason=_skip_reason(skip, 'SDK version {}'.format(version))
    )


def _is_sdk_below(version):
    return _compare_versions(ovirtsdk4.version.VERSION, version) < 0


def _skip_reason(skip, version):
    return 'Only supported since {}'.format(version) if skip else ''


def _compare_versions(runtime_version, candidate_version):
    """
    :param runtime_version: version number as string or 'master'
    :param candidate_version: version number as string or 'master'
    :return: -1 if runtime_version is smaller
              0 if versions are equal
              1 if runtime_version version is larger
    """
    if candidate_version == runtime_version:
        return 0
    if runtime_version == 'master':
        return 1
    if candidate_version == 'master':
        return -1
    if LooseVersion(runtime_version) < LooseVersion(candidate_version):
        return -1
    return 1
