#!/usr/bin/python3
import unittest
import amulet


class TestSwarm(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.d = amulet.Deployment(series='trusty')
        cls.d.add('swarm')
        cls.d.add('consul', 'cs:~containers/trusty/consul-0')
        cls.d.configure('swarm', {})
        cls.d.configure('consul', {'bootstrap-expect': 1})
        cls.d.relate('swarm:consul', 'consul:api')
        cls.d.expose('swarm')

        cls.d.setup(timeout=1200)
        cls.d.sentry.wait()

        cls.swarm = cls.d.sentry['swarm'][0]
        cls.consul = cls.d.sentry['consul'][0]

    def test_swarm_manager(self):
        # Are we running the manager?
        out = self.swarm.run('docker ps')
        assert 'swarm_manager_1' in out[0]
        # under no circumstances should the containers
        # be cycling this early.
        assert 'restarting' not in out[0]

    def test_swarm_agent(self):
        # Are we running the agent?
        out = self.swarm.run('docker ps')
        assert 'swarm_agent_1' in out[0]
        # under no circumstances should the containers
        # be cycling this early.
        assert 'restarting' not in out[0]

    def test_consul_storage_configuration(self):
        '''
        Part of modern docker deployments is the backend key/value store that
        the daemon uses for coordination between engines participating in the
        cluster. This allows for interesting things like storage, network,
        and cluster coordination (if you're using swarm)
        '''
        saddrs = self.swarm.relation('consul', 'consul:api')['private-address']
        caddrs = self.consul.relation('api', 'swarm:consul')['private-address']
        out = self.swarm.run('docker info')
        # Validate KV storage
        cstring = 'consul://{}:8500'.format(caddrs)
        assert cstring in out[0]

        # Validate cluster broadcast endpoint
        castring = 'Cluster advertise: {}:2376'.format(saddrs)
        assert castring in out[0]


if __name__ == "__main__":
    unittest.main()
