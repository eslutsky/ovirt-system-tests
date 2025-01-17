#
# Copyright oVirt Authors
# SPDX-License-Identifier: GPL-2.0-or-later
#
#
import pytest

from fixtures.host import ETH1

from ovirtlib import netattachlib
from ovirtlib import netlib
from ovirtlib import hostlib
from ovirtlib import clusterlib


REQ_NET = 'req-net'


@pytest.fixture(scope='module')
def req_net(default_data_center):
    network = netlib.Network(default_data_center)
    network.create(name=REQ_NET, usages=())
    yield network
    network.remove()


@pytest.fixture(scope='module')
def cluster_net(default_cluster, req_net):
    cluster_network = clusterlib.ClusterNetwork(default_cluster)
    cluster_network.assign(req_net, required=False)
    yield cluster_network
    cluster_network.remove()


@pytest.fixture(scope='module')
def cluster_hosts_up(default_cluster, system):
    cluster_host_ids = default_cluster.host_ids()
    cluster_hosts = []
    for host_id in cluster_host_ids:
        host = hostlib.Host(system)
        host.import_by_id(host_id)
        host.wait_for_up_status(timeout=hostlib.HOST_TIMEOUT_LONG)
        cluster_hosts.append(host)
    return cluster_hosts


@pytest.fixture(scope='module')
def cluster_hosts_net_setup(cluster_hosts_up, req_net, cluster_net):
    try:
        for i, host in enumerate(cluster_hosts_up):
            req_att_data = netattachlib.NetworkAttachmentData(
                req_net, ETH1, (netattachlib.NO_V4, netattachlib.NO_V6)
            )
            host.setup_networks([req_att_data])
    except Exception as e:
        # if setup fails for some of the hosts roll it back before aborting
        remove_net_from_hosts(cluster_hosts_up, req_net)
        raise e
    yield cluster_hosts_up
    remove_net_from_hosts(cluster_hosts_up, req_net)


def remove_net_from_hosts(cluster_hosts_up, req_net):
    for host in cluster_hosts_up:
        try:
            host.remove_networks((req_net,))
        except Exception:
            pass


@pytest.fixture(scope='module')
def optionally_non_spm_host(cluster_hosts_net_setup):
    for host in cluster_hosts_net_setup:
        if host.is_not_spm:
            return host
    return cluster_hosts_net_setup[0]


def test_required_network_host_non_operational(
    req_net, cluster_net, optionally_non_spm_host
):
    cluster_net.update(required=True)
    optionally_non_spm_host.remove_networks((req_net,))
    optionally_non_spm_host.wait_for_non_operational_status()
    cluster_net.update(required=False)
    optionally_non_spm_host.activate()
    optionally_non_spm_host.wait_for_up_status()
