from charmhelpers.core import hookenv
from charmhelpers.core import host
from charmhelpers.core.templating import render
from charmhelpers.core import unitdata
from charms.reactive import when
from charms.reactive import when_not
from charms import reactive

from charms.docker import Docker
from charms.docker.dockeropts import DockerOpts
from charms.docker.compose import Compose

from charmhelpers.core.hookenv import status_set
from charmhelpers.core.hookenv import is_leader
from charmhelpers.core.hookenv import leader_get
from charmhelpers.core.hookenv import unit_get

from os import getenv
from os import path
from os import makedirs

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
    addr = hookenv.unit_private_ip()

    databag = {}
    databag.update({'connection_string': con_string,
                    'leader': is_leader(),
                    'charm_dir': getenv('CHARM_DIR'),
                    'advertise': '{}:2376'.format(addr)}
                    )
    # render the docker-compose template
    render('swarm-compose.yml', 'files/swarm/docker-compose.yml', databag)
    c = Compose('files/swarm')
    c.up()

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

    c = Compose('files/swarm')
    c.kill()
    remove_state('swarm.available')
    status_set('waiting', 'Reconfiguring swarm')



def bind_docker_daemon():
    hookenv.status_set('maintenance', 'Configuring Docker for TCP connections')
    opts = DockerOpts()
    opts.add('host', 'tcp://{}:2376'.format(hookenv.unit_private_ip()))
    opts.add('host', 'unix:///var/run/docker.sock')
    render('docker.defaults', '/etc/default/docker', {'opts': opts.to_s()})
    host.service_restart('docker')

@when('server certificate available')
def secure_docker_daemon():
    '''
    '''
    if not path.exists('files/tls'):
        makedirs('files/tls')

    kv = unitdata.kv()
    cert = kv.get('tls.server.certificate')
    with open('files/tls/docker.server.crt', 'w+') as f:
        f.write(cert)
    with open('files/tls/docker.ca.crt', 'w+') as f:
        f.write(leader_get('certificate_authority'))

    # schenanigans
    keypath = 'easy-rsa/easyrsa3/pki/private/{}.key'
    if path.exists(keypath.format('server')):
        copyfile(keypath.format('server'), 'files/tls/docker.server.key')
    else:
        copyfile(keypath.format(unit_get('public-address')), 'files/tls/docker.server.key')

    opts = DockerOpts()
    charm_dir = getenv('CHARM_DIR')
    cert_path = '{}/docker.server.crt'.format(charm_dir)
    ca_path = '{}/docker.ca.crt'.format(charm_dir)
    key_path = '{}/docker.server.key'.format(charm_dir)
    opts.add('tlscert', cert_path)
    opts.add('tlscacert', ca_path)
    opts.add('tlskey', key_path)
    render('docker.defaults', '/etc/default/docker', {'opts': opts.to_s()})
