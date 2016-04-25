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

@when('easyrsa installed')
@when_not('swarm.tls.config.modified')
def inject_swarm_tls_template():
    """
    layer-tls installs a default OpenSSL Configuration that is incompatibile
    with how swarm expects TLS keys to be generated. We will append what
    we need to the TLS config, and let layer-tls take over from there.
    """
    if not is_leader():
        return
    else:
        status_set('maintenance', 'Reconfiguring SSL PKI configuration')

    print('Updating EasyRSA3 OpenSSL Config')
    openssl_config = 'easy-rsa/easyrsa3/openssl-1.0.cnf'
    with open(openssl_config, 'r') as f:
        existing_template = f.readlines()

    for idx, line in enumerate(existing_template):
        if '[ req ]' in line:
            existing_template.insert(idx + 1, "req_extensions = v3_req\n")

    v3_reqs = ['[ v3_req ]\n',
    'basicConstraints = CA:FALSE\n',
    'keyUsage = nonRepudiation, digitalSignature, keyEncipherment\n',
    'extendedKeyUsage = clientAuth, serverAuth\n']

    swarm_ssl_config = existing_template + v3_reqs

    with open(openssl_config, 'w') as f:
        for line in swarm_ssl_config:
            f.write(line)
    reactive.set_state('swarm.tls.config.modified')
    reactive.set_state('tls.regenerate_certificates')
