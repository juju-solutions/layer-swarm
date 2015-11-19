# Hacking on the swarm layer

The charm strives for full test coverage. Any features you add / patch please
ensure that the included tox tests pass

```
tox
```

If you don't have tox installed, its available over pip

```
pip install tox
```

### Todo Items

- TLS termination of tcp enabled docker socket
- juju-action to provide a "docker workspace configuration"
  - juju action do swarm/0 build-workspace
  - juju action get {{uid}}
  - extract tarball to $HOME/.docker and have the TLS certs, and env config for
  communicating with your new swarm cluster
- Proper leadership resolution in the event of a failure
- payload tracking via payload-register, payload-status-set
- amulet tests to deploy workloads and verify they are running as intended
- integration with a log shipping mechanism to warehouse all app-container logs
- Proper service discovery integration
