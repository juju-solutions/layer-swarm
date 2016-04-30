# Swarm


## Docker Swarm Overview

Docker Swarm is native clustering for Docker. It turns a pool of Docker hosts
into a single, virtual Docker host. Because Docker Swarm serves the standard
Docker API, any tool that already communicates with a Docker daemon can use
Swarm to transparently scale to multiple hosts. Supported tools include, but
are not limited to, the following:

- Dokku
- Docker Compose
- Jenkins

And of course, the Docker client itself is also supported.

## Usage

In order to properly scale and coordinate a swarm cluster, you will need 2
charms. A keyvalue store like Consul or Etcd, and the Swarm host(s). To evaluate
the charm as cheaply as possible you can deploy a single node of each:

    juju deploy cs:trusty/etcd
    juju deploy cs:trusty/swarm
    juju expose swarm

This will deploy a single unit etcd application, and a single swarm host,
configured as both a swarm manager, and a participating member in the cluster.

## Using Swarm

By default, the swarm cluter is TLS terminated with self signed PKI, under
coordination from the swarm leader. (This is visible in `juju status` output)

    juju scp swarm/0:swarm_credentials.tar .
    tar xvf swarm_credentials.tar
    cd swarm_credentials
    source enable.sh
    docker info

The `enable.sh` script will load your shell environment with the following
environment variables, allowing you to connect to the swarm service:

- DOCKER_HOST=tcp://{{ ip address of swarm master }}:3376
- DOCKER_CERT_PATH={{present working directory}}
- DOCKER_ENABLE_TLS=1


#### How do I load these credentials into docker-machine?

This is an ongoing effort. There is [a bug in the upstream](https://github.com/docker/machine/issues/1221)
docker-machine project we are tracking to resolution, at which time this will
be possible.



The final line of the usage commands will display information about the status
of your Swarm cluster.

    Containers: 2
     Running: 2
     Paused: 0
     Stopped: 0
    Images: 1
    Server Version: swarm/1.1.3
    Role: primary
    Strategy: spread
    Filters: health, port, dependency, affinity, constraint
    Nodes: 1
     swarm_swarm_1: 55.55.55.55:2376
      └ Status: Healthy
      └ Containers: 2
      └ Reserved CPUs: 0 / 1
      └ Reserved Memory: 0 B / 513.4 MiB
      └ Error: (none)
      └ UpdatedAt: 2016-04-30T18:57:59Z

The output will give you an idea of how loaded your cluster is and how well it
is performing. This output can be handy when debugging cluster behavior, such
as after scaling swarm.


## Run a workload

Once you've established your credentials and verified you can communciate with
the swarm cluster over TLS. You're now ready to launch workloads on your
swarm cluster.

This can be done via the docker cli, docker-compose, or with
Juju Charms that are written using [layer-docker](https://github.com/juju-solutions/layer-docker).
