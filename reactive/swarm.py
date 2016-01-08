from charmhelpers.core import hookenv
from charmhelpers.core import host
from charmhelpers.core.templating import render
from charms.reactive import when
from charms.reactive import when_not
from charms import reactive

from charms.docker import Docker
from charms.docker.dockeropts import DockerOpts
from charms.docker.compose import Compose

from charmhelpers.core.hookenv import status_set
from charmhelpers.core.hookenv import is_leader

from shlex import split
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

    opts = {}
    opts['connection_string'] = con_string
    opts['addr'] = hookenv.unit_private_ip()
    opts['port'] = 2375
    opts['leader'] = is_leader()

    render('docker-compose.yml', 'files/swarm/docker-compose.yml', opts)
    compose = Compose('files/swarm')
    compose.up()
    hookenv.open_port(2376)
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
    c.rm()
    remove_state('swarm.available')
    status_set('waiting', 'Reconfiguring swarm')

def bind_docker_daemon():
    hookenv.status_set('maintenance', 'Configuring Docker for TCP connections')
    opts = DockerOpts()
    opts.add('host', 'tcp://{}:2375'.format(hookenv.unit_private_ip()))
    opts.add('host', 'unix:///var/run/docker.sock')
    render('docker.defaults', '/etc/default/docker', {'opts': opts.to_s()})
    host.service_restart('docker')
