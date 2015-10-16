import abc
from lab.WithConfig import WithConfig
from lab.WithRunMixin import WithRunMixin


class Runner(WithConfig, WithRunMixin):
    @abc.abstractmethod
    def execute(self, clouds, servers):
        pass

    @staticmethod
    def get_artefacts(server):
        configs = ['version:\n{0}'.format(server.run('rpm -qi rpm -qi python-networking-cisco'))]
        for x in ['vlan_ranges', 'ucsm', 'api_workers']:
            cmd = 'sudo grep -r {0} /etc/neutron/* | grep -v \#'.format(x)
            configs.append('\n{0} gives:\n {1}'.format(cmd, server.run(cmd)))

        cmd = 'sudo grep -i ERROR /var/log/neutron/* | grep -i ucsm'
        configs.append('\n{0} gives:\n {1}'.format(cmd, server.run(cmd)))
        return '\n\n'.join(configs)
