#
# Copyright oVirt Authors
# SPDX-License-Identifier: GPL-2.0-or-later
#
from collections import namedtuple
import logging
import pytest

from fixtures.host import ETH1

from ovirtlib import clusterlib
from ovirtlib import hostlib
from ovirtlib import joblib
from ovirtlib import netattachlib
from ovirtlib import netlib
from ovirtlib import sshlib
from ovirtlib import virtlib

from testlib import suite

PORT_ISOLATION_NET = 'test_port_isolation_net'
VM_USERNAME = 'cirros'
VM_PASSWORD = 'gocubsgo'
PING_FAILED = '100% packet loss'
EXTERNAL_IP = {'inet': '8.8.8.8', 'inet6': '2001:4860:4860::8888'}
Iface = namedtuple('Iface', ['name', 'ipv6'])
VMS = [
    {
        'name': 'test_port_isolation_vm_0',
        'mgmt': Iface('eth0', 'fd8f:1391:3a82:202::cafe:00'),
        'isolate': Iface('eth1', 'fd8f:1391:3a82:201::cafe:10'),
    },
    {
        'name': 'test_port_isolation_vm_1',
        'mgmt': Iface('eth0', 'fd8f:1391:3a82:202::cafe:01'),
        'isolate': Iface('eth1', 'fd8f:1391:3a82:201::cafe:11'),
    },
]

LOGGER = logging.getLogger(__name__)


@pytest.mark.xfail(
    suite.af().is6, reason='CI lab does not provide external ipv6 connectivity'
)
def test_ping_to_external_port_succeeds(vm_nodes, isolated_ifaces_up_with_ip):
    for i, vm_node in enumerate(vm_nodes):
        vm_node.ping(EXTERNAL_IP[suite.af().family], VMS[i]['isolate'].name)


def test_ping_to_mgmt_port_succeeds(vm_nodes, mgmt_ifaces_up_with_ip):
    vm_nodes[0].ping(mgmt_ifaces_up_with_ip[1], VMS[0]['mgmt'].name)
    vm_nodes[1].ping(mgmt_ifaces_up_with_ip[0], VMS[1]['mgmt'].name)


def test_ping_to_isolated_port_fails(vm_nodes, isolated_ifaces_up_with_ip):
    with pytest.raises(sshlib.SshException, match=PING_FAILED):
        vm_nodes[0].ping(isolated_ifaces_up_with_ip[1])
    with pytest.raises(sshlib.SshException, match=PING_FAILED):
        vm_nodes[1].ping(isolated_ifaces_up_with_ip[0])


@pytest.fixture(scope='module')
def vm_nodes(mgmt_ifaces_up_with_ip):
    return (
        sshlib.CirrosNode(mgmt_ifaces_up_with_ip[0], VM_PASSWORD, VM_USERNAME),
        sshlib.CirrosNode(mgmt_ifaces_up_with_ip[1], VM_PASSWORD, VM_USERNAME),
    )


@pytest.fixture(scope='module')
def mgmt_ifaces_up_with_ip(vms_up_on_host_1, cirros_serial_console):
    return _assign_ips_on_vms_ifaces(
        vms_up_on_host_1, cirros_serial_console, 'mgmt'
    )


@pytest.fixture(scope='module')
def isolated_ifaces_up_with_ip(vms_up_on_host_1, cirros_serial_console):
    ips = _assign_ips_on_vms_ifaces(
        vms_up_on_host_1, cirros_serial_console, 'isolate'
    )
    for vm in vms_up_on_host_1:
        ip_a = cirros_serial_console.shell(vm.id, ('ip addr',))
        LOGGER.debug(f'after applying ips: vm={vm.name} has ip_a={ip_a}')
    return ips


def _assign_ips_on_vms_ifaces(vms, serial_console, iface_usage):
    ips = []
    for i, vm in enumerate(vms):
        iface = VMS[i][iface_usage]
        if suite.af().is6:
            ip = iface.ipv6
            serial_console.add_static_ip(vm.id, f'{ip}/128', iface.name)
        else:
            ip = serial_console.assign_ip4_if_missing(vm.id, iface.name)
        ips.append(ip)
    return ips


@pytest.fixture(scope='module')
def vms_up_on_host_1(
    system,
    default_cluster,
    cirros_template,
    port_isolation_network,
    ovirtmgmt_vnic_profile,
    cirros_serial_console,
):
    """
    Since the isolated_network is set up only on host_1,
    both virtual machines will be on it.
    """
    with virtlib.vm_pool(system, size=2) as (vm_0, vm_1):
        for i, vm in enumerate([vm_0, vm_1]):
            vm.create(
                vm_name=VMS[i]['name'],
                cluster=default_cluster,
                template=cirros_template,
            )
            vm_vnic0 = netlib.Vnic(vm)
            vm_vnic0.create(
                name=VMS[i]['mgmt'].name, vnic_profile=ovirtmgmt_vnic_profile
            )
            vm_vnic1 = netlib.Vnic(vm)
            vm_vnic1.create(
                name=VMS[i]['isolate'].name,
                vnic_profile=port_isolation_network.vnic_profile(),
            )
            vm.wait_for_down_status()
            vm.run_once(cloud_init_hostname=VMS[i]['name'])

        vm_0.wait_for_up_status()
        vm_1.wait_for_up_status()
        joblib.AllJobs(system).wait_for_done()
        for vm in (vm_0, vm_1):
            ip_a = cirros_serial_console.shell(vm.id, ('ip addr',))
            LOGGER.debug(f'before applying ips: vm={vm.name} has ip_a={ip_a}')
        yield vm_0, vm_1


@pytest.fixture(scope='module')
def port_isolation_network(default_data_center, default_cluster, host_1_up):
    with clusterlib.new_assigned_network(
        PORT_ISOLATION_NET,
        default_data_center,
        default_cluster,
        port_isolation=True,
    ) as network:
        attach_data = netattachlib.NetworkAttachmentData(
            network, ETH1, (netattachlib.DYNAMIC_IP_ASSIGN[suite.af().family],)
        )
        with hostlib.setup_networks(host_1_up, attach_data=(attach_data,)):
            yield network
