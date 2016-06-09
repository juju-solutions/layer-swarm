from charms.docker import DockerOpts
from charms.docker import Compose

from charms.leadership import leader_set
from charms.leadership import leader_get

from charms.reactive import remove_state
from charms.reactive import set_state
from charms.reactive import when
from charms.reactive import when_any
from charms.reactive import when_not

from charmhelpers.core.hookenv import is_leader
from charmhelpers.core.hookenv import log
from charmhelpers.core.hookenv import status_set
from charmhelpers.core.hookenv import unit_get
from charmhelpers.core.hookenv import open_port
from charmhelpers.core.hookenv import unit_private_ip
from charmhelpers.core import unitdata
from charmhelpers.core.host import service_restart
from charmhelpers.core.templating import render

from os import getenv
from os import makedirs
from os import path
from os import remove

from shlex import split
from shutil import copyfile

from tlslib import client_cert
from tlslib import client_key
from tlslib import ca

import subprocess
import charms.leadership  # noqa


@when('etcd.available', 'docker.available')
@when_not('swarm.available')
def swarm_etcd_cluster_setup(etcd):
    """
    Expose the Docker TCP port, and begin swarm cluster configuration. Always
    leading with the agent, connecting to the discovery service, then follow
    up with the manager container on the leader node.
    """
    opts = DockerOpts()
    # capture and place etcd TLS certificates
    certs = etcd.ssl_certificates()
    unit_name = getenv('JUJU_UNIT_NAME').replace('/', '-')
    cert_path = '/etc/ssl/{}/'.format(unit_name)

    if not path.exists(cert_path):
        makedirs(cert_path)

    # favor the data on the wire always, and re-write the certificates
    if certs['client_cert']:
        with open('{}/{}'.format(cert_path, 'client-cert.pem'), 'w+') as fp:
            fp.write(certs['client_cert'])

    if certs['client_key']:
        with open('{}/{}'.format(cert_path, 'client-key.pem'), 'w+') as fp:
            fp.write(certs['client_key'])

    if certs['client_ca']:
        with open('{}/{}'.format(cert_path, 'client-ca.pem'), 'w+') as fp:
            fp.write(certs['client_ca'])

    # format the connection string based on presence of encryption in the
    # connection string. Docker is the only known suite of tooling to use
    # the etcd:// protocol uri... dubious

    secure_discovery = 'https' in etcd.connection_string()
    if secure_discovery:
        con_string = etcd.connection_string().replace('https', 'etcd')
        cert = 'kv.certfile={}/client-cert.pem'.format(cert_path)
        key = 'kv.certfile={}/client-key.pem'.format(cert_path)
        opts.add('cluster-store-opt', cert)
        opts.add('cluster-store-opt', key)
    else:
        con_string = etcd.connection_string().replace('http', 'etcd')

    bind_docker_daemon(con_string)

    if secure_discovery:
        start_swarm(con_string, cert_path)
    else:
        start_swarm(con_string)

    status_set('active', 'Swarm configured. Happy swarming')


@when('consul.available', 'docker.available')
@when_not('swarm.available')
def swarm_consul_cluster_setup(consul):
    connection_string = "consul://"
    for unit in consul.list_unit_data():
        host_string = "{}:{}".format(unit['address'], unit['port'])
        connection_string = "{}{},".format(connection_string, host_string)
    bind_docker_daemon(connection_string.rstrip(','))
    start_swarm(connection_string.rstrip(','))


def start_swarm(cluster_string, cert_path=None):
    ''' Render the compose configuration and start the swarm scheduler '''
    opts = {}
    opts['addr'] = unit_private_ip()
    opts['port'] = 2376
    opts['leader'] = is_leader()
    opts['connection_string'] = cluster_string
    if cert_path:
        opts['discovery_tls_path'] = cert_path
    render('docker-compose.yml', 'files/swarm/docker-compose.yml', opts)
    c = Compose('files/swarm')
    c.up()
    set_state('swarm.available')


@when('leadership.is_leader')
@when('swarm.available')
def swarm_leader_messaging():
    status_set('active', 'Swarm leader running')


@when_not('leadership.is_leader')
@when('swarm.available')
def swarm_follower_messaging():
    status_set('active', 'Swarm follower')


@when_not('etcd.connected', 'consul.connected')
def user_notice():
    """
    Notify the user they need to relate the charm with ETCD or Consul to
    trigger the swarm cluster configuration.
    """
    status_set('waiting', 'Waiting on Etcd or Consul relation')


@when('swarm.available')
@when_not('etcd.connected', 'consul.connected')
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


@when('easyrsa installed')
@when_not('swarm.tls.opensslconfig.modified')
def inject_swarm_tls_template():
    """
    layer-tls installs a default OpenSSL Configuration that is incompatibile
    with how swarm expects TLS keys to be generated. We will append what
    we need to the x509-type, and poke layer-tls to regenerate.
    """

    status_set('maintenance', 'Reconfiguring SSL PKI configuration')

    log('Updating EasyRSA3 OpenSSL Config')
    openssl_config = 'easy-rsa/easyrsa3/x509-types/server'

    with open(openssl_config, 'r') as f:
        existing_template = f.readlines()

    # use list comprehension to enable clients,server usage for certificates
    # with the docker/swarm daemons.
    xtype = [w.replace('serverAuth', 'serverAuth, clientAuth') for w in existing_template]  # noqa
    with open(openssl_config, 'w+') as f:
        f.writelines(xtype)

    set_state('swarm.tls.opensslconfig.modified')
    set_state('easyrsa configured')


@when('tls.server.certificate available')
def enable_client_tls():
    """
    Copy the TLS certificates in place and generate mount points for the swarm
    manager to mount the certs. This enables client-side TLS security on the
    TCP service.
    """
    if not path.exists('/etc/docker'):
        makedirs('/etc/docker')

    kv = unitdata.kv()
    cert = kv.get('tls.server.certificate')
    with open('/etc/docker/server.pem', 'w+') as f:
        f.write(cert)
    with open('/etc/docker/ca.pem', 'w+') as f:
        f.write(leader_get('certificate_authority'))

    # schenanigans
    keypath = 'easy-rsa/easyrsa3/pki/private/{}.key'
    server = getenv('JUJU_UNIT_NAME').replace('/', '_')
    if path.exists(keypath.format(server)):
        copyfile(keypath.format(server), '/etc/docker/server-key.pem')
    else:
        copyfile(keypath.format(unit_get('public-address')),
                 '/etc/docker/server-key.pem')

    opts = DockerOpts()
    config_dir = '/etc/docker'
    cert_path = '{}/server.pem'.format(config_dir)
    ca_path = '{}/ca.pem'.format(config_dir)
    key_path = '{}/server-key.pem'.format(config_dir)
    opts.add('tlscert', cert_path)
    opts.add('tlscacert', ca_path)
    opts.add('tlskey', key_path)
    opts.add('tlsverify', None)
    render('docker.defaults', '/etc/default/docker', {'opts': opts.to_s()})


@when('leadership.is_leader')
@when('tls.client.certificate available')
@when_not('leadership.set.client_cert', 'leadership.set.client_key')
def prepare_default_client_credentials():
    """ Generate a downloadable package for clients to use to speak to the
    swarm cluster. """

    # Leverage TLSLib to copy the default cert from PKI
    client_cert(None, './swarm_credentials/cert.pem')
    client_key(None, './swarm_credentials/key.pem')
    ca(None, './swarm_credentials/ca.pem')

    with open('swarm_credentials/key.pem', 'r') as fp:
        key_contents = fp.read()
    with open('swarm_credentials/cert.pem', 'r') as fp:
        crt_contents = fp.read()

    leader_set({'client_cert': crt_contents,
                'client_key': key_contents})


@when_any('leadership.changed.client_cert', 'leadership.changed.client_key')
@when_not('client.credentials.placed')
def prepare_end_user_package():
    """ Prepare the tarball package for clients to use to connet to the
        swarm cluster using the default client credentials. """

    # If we are a follower, we dont have keys and need to fetch them
    # from leader-data, which triggered `leadership.set.client_cert`
    # So it better be there!
    if not path.exists('swarm_credentials'):
        makedirs('swarm_credentials')
        with open('swarm_credentials/key.pem', 'w+') as fp:
            fp.write(leader_get('client_key'))
        with open('swarm_credentials/cert.pem', 'w+') as fp:
            fp.write(leader_get('client_cert'))
        with open('swarm_credentials/ca.pem', 'w+') as fp:
            fp.write(leader_get('certificate_authority'))

    # Render the client package script
    template_vars = {'public_address': unit_get('public-address')}
    render('enable.sh', './swarm_credentials/enable.sh', template_vars)

    # clear out any stale credentials package
    if path.exists('swarm_credentials.tar'):
        remove('swarm_credentials.tar')

    cmd = 'tar cvfz swarm_credentials.tar.gz swarm_credentials'
    subprocess.check_call(split(cmd))
    copyfile('swarm_credentials.tar.gz',
             '/home/ubuntu/swarm_credentials.tar.gz')
    set_state('client.credentials.placed')


@when('leadership.is_leader')
def open_swarm_manager_port():
    open_port(3376)
    # Tell the followers where to connect to the manager for internal
    # operations.
    leader_set({'swarm_manager': 'tcp://{}:3376'.format(unit_private_ip())})


def bind_docker_daemon(connection_string):
    """ Bind the docker daemon to a TCP socket with TLS credentials """
    status_set('maintenance', 'Configuring Docker for TCP connections')
    opts = DockerOpts()
    private_address = unit_private_ip()
    opts.add('host', 'tcp://{}:2376'.format(private_address))
    opts.add('host', 'unix:///var/run/docker.sock')
    opts.add('cluster-advertise', '{}:2376'.format(private_address))
    opts.add('cluster-store', connection_string, strict=True)
    render('docker.defaults', '/etc/default/docker', {'opts': opts.to_s()})
    service_restart('docker')
    open_port(2376)
