#
# Copyright oVirt Authors
# SPDX-License-Identifier: GPL-2.0-or-later
#
#
import ipaddress
import pytest

from fixtures.host import ETH1

from ovirtlib import virtlib
from ovirtlib import netattachlib
from ovirtlib import netlib
from ovirtlib import clusterlib
from ovirtlib import hostlib
from ovirtlib import joblib
from ovirtlib import datacenterlib
from ovirtlib import templatelib
from testlib import suite

VM_BLANK = 'test_vm_operations_blank_vm'
VM_CIRROS = 'test_vm_operations_cirros_vm'
MIG_NET = 'mig-net'
NIC1_NAME = 'nic1'
NIC2_NAME = 'nic2'
SERIAL_NET = 'test_serial_vmconsole_net'
CIRROS_NIC = 'eth1'
IPV6 = 'fd8f:1391:3a82::cafe:cafe'
PREFIX = '64'
STATIC_ASSIGN_1 = {
    'inet': netattachlib.StaticIpv4Assignment('192.0.3.1', '255.255.255.0'),
    'inet6': netattachlib.StaticIpv6Assignment('fd8f:192:0:3::1', '64'),
}
STATIC_ASSIGN_2 = {
    'inet': netattachlib.StaticIpv4Assignment('192.0.3.2', '255.255.255.0'),
    'inet6': netattachlib.StaticIpv6Assignment('fd8f:192:0:3::2', '64'),
}


@pytest.fixture
def migration_network(host_0, host_1, default_data_center, default_cluster):
    network = netlib.Network(default_data_center)
    network.create(name=MIG_NET, usages=())
    cluster_network = clusterlib.ClusterNetwork(default_cluster)
    cluster_network.assign(network)
    cluster_network.set_usages([netlib.NetworkUsage.MIGRATION])
    yield network
    network.remove()


@pytest.fixture
def running_cirros_vm(
    system,
    default_data_center,
    default_cluster,
    default_storage_domain,
    ovirtmgmt_vnic_profile,
    host_1_up,
    cirros_template,
):
    with clusterlib.new_assigned_network(
        SERIAL_NET, default_data_center, default_cluster
    ) as net:
        attach_data = netattachlib.NetworkAttachmentData(net, ETH1)
        with hostlib.setup_networks(host_1_up, attach_data=(attach_data,)):
            with virtlib.vm_pool(system, size=1) as (vm,):
                vm.create(
                    vm_name=VM_CIRROS,
                    cluster=default_cluster,
                    template=cirros_template,
                )
                vm.create_vnic(NIC1_NAME, ovirtmgmt_vnic_profile)
                vm.create_vnic(NIC2_NAME, net.vnic_profile())
                vm.wait_for_down_status()
                vm.run()
                vm.wait_for_up_status()
                joblib.AllJobs(system).wait_for_done()
                yield vm


@pytest.fixture(scope='module')
def running_blank_vm(
    system, default_cluster, default_storage_domain, ovirtmgmt_vnic_profile
):
    disk = default_storage_domain.create_disk('disk0')
    with virtlib.vm_pool(system, size=1) as (vm,):
        vm.create(
            vm_name=VM_BLANK,
            cluster=default_cluster,
            template=templatelib.TEMPLATE_BLANK,
        )
        vm.create_vnic(NIC1_NAME, ovirtmgmt_vnic_profile)
        disk_att_id = vm.attach_disk(disk=disk)
        vm.wait_for_disk_up_status(disk, disk_att_id)
        vm.run()
        vm.wait_for_up_status()
        joblib.AllJobs(system).wait_for_done()
        yield vm


@pytest.fixture
def host_0_with_mig_net(migration_network, host_0_up):
    mig_att_data = netattachlib.NetworkAttachmentData(
        migration_network, ETH1, (STATIC_ASSIGN_1[suite.af().family],)
    )
    host_0_up.setup_networks([mig_att_data])
    yield host_0_up
    host_0_up.remove_networks((migration_network,))


@pytest.fixture
def host_1_with_mig_net(migration_network, host_1_up):
    mig_att_data = netattachlib.NetworkAttachmentData(
        migration_network, ETH1, (STATIC_ASSIGN_2[suite.af().family],)
    )
    host_1_up.setup_networks([mig_att_data])
    yield host_1_up
    host_1_up.remove_networks((migration_network,))


def test_serial_vmconsole(cirros_serial_console, running_cirros_vm):
    if suite.af().is6:
        ip = cirros_serial_console.add_static_ip(
            running_cirros_vm.id, f'{IPV6}/{PREFIX}', CIRROS_NIC
        )
        assert ip == IPV6
    else:
        ip = cirros_serial_console.assign_ip4(running_cirros_vm.id, CIRROS_NIC)
        assert ipaddress.ip_address(ip).version == 4


def test_live_vm_migration_using_dedicated_network(
    running_blank_vm, host_0_with_mig_net, host_1_with_mig_net
):
    dst_host = (
        host_0_with_mig_net
        if running_blank_vm.host.id == host_1_with_mig_net.id
        else host_1_with_mig_net
    )

    running_blank_vm.migrate(dst_host.name)
    running_blank_vm.wait_for_up_status()

    # TODO: verify migration was carried via the dedicated network
    assert running_blank_vm.host.id == dst_host.id


def test_hot_linking_vnic(running_blank_vm):
    vnic = running_blank_vm.get_vnic(NIC1_NAME)
    assert vnic.linked is True

    vnic.linked = False
    vnic = running_blank_vm.get_vnic(NIC1_NAME)
    assert not vnic.linked

    vnic.linked = True
    vnic = running_blank_vm.get_vnic(NIC1_NAME)
    assert vnic.linked is True


def test_iterators(running_blank_vm, system):
    vm_names = (vm.name for vm in virtlib.Vm.iterate(system))
    assert running_blank_vm.name in vm_names

    cluster_names = (
        cluster.name for cluster in clusterlib.Cluster.iterate(system)
    )
    assert running_blank_vm.cluster.name in cluster_names

    vnic_names = (vnic.name for vnic in running_blank_vm.vnics())
    assert NIC1_NAME in vnic_names

    vnic_profile_names = (
        profile.name for profile in netlib.VnicProfile.iterate(system)
    )
    assert (
        next(running_blank_vm.vnics()).vnic_profile.name in vnic_profile_names
    )

    dc_names = (dc.name for dc in datacenterlib.DataCenter.iterate(system))
    assert running_blank_vm.cluster.get_data_center().name in dc_names

    assert (
        len(
            list(
                datacenterlib.DataCenter.iterate(
                    system, search='name = missing'
                )
            )
        )
        == 0
    )


def test_assign_network_filter(running_blank_vm, system, ovirtmgmt_network):
    with netlib.create_vnic_profile(
        system, 'temporary', ovirtmgmt_network
    ) as profile:
        network_filter = netlib.NetworkFilter(system)
        network_filter.import_by_name('allow-dhcp')
        profile.filter = network_filter

        vnic = next(running_blank_vm.vnics())
        original_profile = vnic.vnic_profile

        try:
            vnic.vnic_profile = profile
            assert vnic.vnic_profile.name == 'temporary'
            assert vnic.vnic_profile.filter.name == 'allow-dhcp'
        finally:
            vnic.vnic_profile = original_profile


@suite.skip_suites_below('4.3')
def test_hot_update_vm_interface(running_blank_vm, ovirtmgmt_vnic_profile):
    vnic = netlib.Vnic(running_blank_vm)
    vnic.create(name=NIC2_NAME, vnic_profile=netlib.EmptyVnicProfile())
    assert not vnic.vnic_profile.id

    vnic.vnic_profile = ovirtmgmt_vnic_profile
    assert vnic.vnic_profile.name == ovirtmgmt_vnic_profile.name

    vnic.vnic_profile = netlib.EmptyVnicProfile()
    assert not vnic.vnic_profile.id
