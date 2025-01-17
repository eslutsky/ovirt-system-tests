#
# Copyright oVirt Authors
# SPDX-License-Identifier: GPL-2.0-or-later
#

import pytest

from ovirtlib import hostlib
from ovirtlib.sdkentity import EntityNotFoundError


ETH0 = 'eth0'
ETH1 = 'eth1'
ETH2 = 'eth2'
ETH3 = 'eth3'


@pytest.fixture(scope='session')
def host_0(system, default_cluster, host0_facts):
    return _create_host(system, default_cluster, host0_facts)


@pytest.fixture(scope='session')
def host_0_up(system, host_0):
    _wait_for_host_install(system, host_0)
    return host_0


@pytest.fixture(scope='session')
def host_1(system, default_cluster, host1_facts):
    return _create_host(system, default_cluster, host1_facts)


@pytest.fixture(scope='session')
def host_1_up(system, host_1):
    _wait_for_host_install(system, host_1)
    return host_1


@pytest.fixture(scope='session')
def host_in_ovs_cluster(
    system, ovs_cluster, default_cluster, default_data_center
):
    host = _non_spm_host(system, default_cluster.host_ids())
    host.wait_for_up_status(timeout=hostlib.HOST_TIMEOUT_LONG)
    with host.toggle_cluster(ovs_cluster):
        host.sync_all_networks()
        host.wait_for_networks_in_sync()
        yield host
    host.sync_all_networks()
    host.wait_for_networks_in_sync()


def _non_spm_host(system, host_ids):
    for host_id in host_ids:
        host = hostlib.Host(system)
        host.import_by_id(host_id)
        if host.is_not_spm or id == host_ids[-1]:
            return host


def _wait_for_host_install(system, host):
    host.wait_for_up_status(timeout=hostlib.HOST_TIMEOUT_LONG)
    results = host.workaround_bz_1779280()
    if isinstance(results[-1], Exception):
        raise results[-1]


@pytest.fixture(scope='session', autouse=True)
def install_hosts_to_save_time(host_0, host_1):
    """add hosts before any test starts so they can install in parallel"""
    pass


def _create_host(system, default_cluster, host_facts):
    host = hostlib.Host(system)
    try:
        host.import_by_name(host_facts.hostname)
        host.root_password = host_facts.ssh_password
    except EntityNotFoundError:
        host.create(
            default_cluster,
            host_facts.hostname,
            host_facts.default_ip(),
            host_facts.ssh_password,
        )
    return host
