from lab.cloud import CloudObject


class CloudPort(CloudObject):
    STATUS_DOWN = 'DOWN'

    def __init__(self, cloud, dic):
        super(CloudPort, self).__init__(cloud=cloud, dic=dic)
        self.subnet_id = dic['fixed_ips'].split('\"')[3]
        self.mac = dic['mac_address']
        self.ip = dic['fixed_ips'].split('\"')[-2]

    @staticmethod
    def create(cloud, server_number, on_nets, sriov=False):
        sriov_addon = '--binding:vnic-type direct' if sriov else ''
        ports = []
        for net in on_nets:
            ip, mac = net.calc_ip_and_mac(server_number)
            fixed_ip_addon = '--fixed-ip ip_address={ip} --mac-address {mac}'.format(ip=ip, mac=mac) if ip else ''
            port_name = CloudObject.UNIQUE_PATTERN_IN_NAME + str(server_number) + '-p' + ('-srvio' if sriov else '') + '-on-' + net.net_name
            l = cloud.os_cmd(['neutron port-create  --name {port_name} {net_name} {ip_addon} {sriov_addon}'.format(port_name=port_name, net_name=net.net_name, ip_addon=fixed_ip_addon, sriov_addon=sriov_addon)])
            port = CloudPort(cloud=cloud, dic=l[0])
            ports.append(port)
        return ports
