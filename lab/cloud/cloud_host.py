from lab.server import Server


class CloudHost(Server):

    def __init__(self, cloud, host_ip, host_id):
        self.cloud = cloud
        self.host_ip = host_ip
        self.host_id = host_id
        ip = cloud.mediator.ip if type(cloud.mediator) is Server else cloud.mediator.ssh_ip
        super(CloudHost, self).__init__(ip=ip, username=self.SQE_USERNAME, password=None)

    def __repr__(self):
        return self.host_id or 'No yet '

    def host_exe(self, cmd):
        cmd = 'ssh -o StrictHostKeyChecking=no root@' + self.host_id + " '" + cmd + "'"
        return self.exe(cmd=cmd, is_warn_only=True)

    @staticmethod
    def host_list(cloud):
        hosts = cloud.os_cmd(['openstack host list -f json'])[0]
        etc_hosts = {x.split()[1]: x.split()[0] for x in cloud.mediator.exe('cat /etc/hosts').split('\r\n') if 'localhost' not in x}
        control_ids = set([x['Host Name'] for x in hosts if x['Service'] == 'scheduler'])
        compute_ids = set([x['Host Name'] for x in hosts if x['Service'] == 'compute'])

        assert len(control_ids - set(etc_hosts)) == 0 and len(compute_ids - set(etc_hosts)) == 0

        controls = [CloudHost(cloud=cloud, host_ip= etc_hosts[x], host_id=x) for x in control_ids]
        computes = []
        for comp_id in compute_ids:
            c = CloudHost(cloud=cloud, host_ip=etc_hosts[comp_id], host_id=comp_id)
            computes.append(c)
            a = c.host_exe('compute crudini --get /etc/nova/nova.conf serial_console enabled && compute crudini --get /etc/nova/nova.conf serial_console proxyclient_address')
            if a.split('\r\n')[0] == 'true' and a.split('\r\n')[1] == c.host_ip:
                continue
            c.host_exe('compute crudini --set /etc/nova/nova.conf serial_console enabled true && compute crudini --set /etc/nova/nova.conf serial_console proxyclient_address {} && systemctl restart docker-novacpu'.format(c.host_ip))

        return controls, computes
