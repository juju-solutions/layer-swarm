# Layer for Swarm

This is a reactive layer for Docker Swarm. A multi-host scheduler for application
container workloads. This layer is intended to extend the [docker layer](http://github.com/juju-solutions/layer-docker) to provide an elastic
compute cluster by extending the basic docker features, allowing the charm
author to launch their containerized workloads across any of the hosts by
communicating with the swarm scheduler in leu of the local docker daemon.

### Reactive States

`swarm.available` Once the swarm.available state has been reached, the charm
has settled and declared its resource to the cluster. Any subsequent container
launches can and should be targeted at the swarm cluster manager on port **2377**

## Usage

To build your own swarm cluster, or to extend an existing charm with swarm
properties:

in your `layer.yaml`

```yaml
includes: ['layer: docker', 'layer:swarm']
```

This will ensure you have the latest Docker binary installed, and have the
swarm cluster configuration included as well. Optionally you can include a SDN
layer, such as flannel:

```yaml
includes: ['layer:docker', 'layer:swarm', 'layer:flannel']
```

Which will enable cross-host container communication, via reconfiguring the
docker bridge to use the flannel overlay network.

## Deployment

This formation depends on the swarm node(s), and an ETCD service for coordination.

juju deploy swarm
juju deploy etcd
juju add-relation swarm etcd

Once the cluster has settled, you can communicate with the swarm daemon

```bash
export DOCKER_HOST=tcp://{{ip-of-master}}:2377
docker info
```

## Known Caveats

See the `hacking.md` document to track the latest development, what our focus is
for the future of the swarm layer, and how to contribute.
