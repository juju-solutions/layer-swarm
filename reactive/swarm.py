from charmhelpers.core import hookenv
from charmhelpers.core import host
from charmhelpers.core.templating import render
from charmhelpers.core import unitdata
from charms.reactive import when
from charms.reactive import when_not
from charms import reactive

from charms.docker import Docker
from charms.docker.dockeropts import DockerOpts

from charmhelpers.core.hookenv import status_set
from charmhelpers.core.hookenv import is_leader
from charmhelpers.core.hookenv import leader_get

from os import getenv
from os import path

from shlex import split
from shutil import copyfile
from subprocess import check_call


@when('etcd.available', 'docker.available')
@when_not('swarm.available')
def swarm_etcd_cluster_setup(etcd):
    """
    Expose the Docker TCP port, and begin swarm cluster configuration. Always
    leading with the agent, connecting to the discovery service, then follow
    up with the manager container on the leader node.
    """
    bind_docker_daemon()
    con_string = etcd.connection_string().replace('http', 'etcd')
    start_swarm_etcd_agent(con_string)
    if hookenv.is_leader():
        start_swarm_etcd_manager(con_string)
    reactive.set_state('swarm.available')
    hookenv.status_set('active', 'Swarm configured. Happy swarming')


@when('swarm.available')
def swarm_messaging():
    if is_leader():
        status_set('active', 'Swarm leader running')
    else:
        status_set('active', 'Swarm follower')


@when_not('etcd.connected')
def user_notice():
    """
    Notify the user they need to relate the charm with ETCD to trigger the
    swarm cluster configuration.
    """
    hookenv.status_set('blocked', 'Pending ETCD connection for swarm')


@when('swarm.available')
@when_not('etcd.connected')
def swarm_relation_broken():
    """
    Destroy the swarm agent, and optionally the manager.
    This state should only be entered if the Docker host relation with ETCD has
    been broken, thus leaving the cluster without a discovery service
    """
    cmd = "docker kill swarmagent"
    try:
        check_call(split(cmd))
    except:
        pass
    if hookenv.is_leader():
        cmd = "docker kill swarmmanger"
        try:
            check_call(split(cmd))
        except:
            pass
    status_set('waiting', 'Reconfiguring swarm')


def start_swarm_etcd_agent(connection_string):
    hookenv.status_set('maintenance', 'starting swarm agent')
    addr = hookenv.unit_private_ip()
    # TODO: refactor to be process run
    cmd = "docker run --restart always -d --name swarmagent swarm join --advertise={0}:{1} {2}/swarm".format(addr, 2375, connection_string)  # noqa
    check_call(split(cmd))
    hookenv.open_port(2375)


def start_swarm_etcd_manager(connection_string):
    hookenv.status_set('maintenance', 'Starting swarm manager')
    # TODO: refactor to be process run
    cmd = "docker run  --restart always -d --name swarmmanager -p 2377:2375 swarm manage {}/swarm".format(connection_string)  # noqa
    check_call(split(cmd))
    hookenv.open_port(2377)


def bind_docker_daemon():
    hookenv.status_set('maintenance', 'Configuring Docker for TCP connections')
    opts = DockerOpts()
    opts.add('host', 'tcp://{}:2375'.format(hookenv.unit_private_ip()))
    opts.add('host', 'unix:///var/run/docker.sock')
    render('docker.defaults', '/etc/default/docker', {'opts': opts.to_s()})
    host.service_restart('docker')

@when('server certificate available')
def secure_docker_daemon():
    '''
    '''
    kv = unitdata.kv()
    cert = kv.get('tls.server.certificate')
    with open('docker.server.crt', 'w+') as f:
        f.write(cert)
    with open('docker.ca.crt', 'w+') as f:
        f.write(leader_get('certificate_authority'))

    # schenanigans
    keypath = 'easy-rsa/easyrsa3/pki/private/{}.key'
    if path.exists(keypath.format('server')):
        copyfile(keypath.format('server'), 'docker.server.key')
    else:
        copyfile(keypath.format(unit_get('public-address')), 'docker.server.key')

    opts = DockerOpts()
    charm_dir = getenv('CHARM_DIR')
    cert_path = '{}/docker.server.crt'.format(charm_dir)
    ca_path = '{}/docker.ca.crt'.format(charm_dir)
    key_path = '{}/docker.server.key'.format(charm_dir)
    opts.add('tlscert', cert_path)
    opts.add('tlscacert', ca_path)
    opts.add('tlskey', key_path)
    render('docker.defaults', '/etc/default/docker', {'opts': opts.to_s()})
