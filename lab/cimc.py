from lab.server import Server


class CimcServer(Server):
    def set_cimc_id(self, server_id):
        pci_bus, n_in_bus = server_id.split('/')  # usually pci_bus/id are the same for all servers, so to make sure macs are different we use here a last octet of ipmi address
        last_ip_octet = str(self._ipmi_ip).split('.')[3]
        self._mac_server_part = 'A{0}:{1:02X}'.format(int(pci_bus), int(last_ip_octet))  # A3:00
        self._form_nics()

    def cleanup(self):
        import ImcSdk
        from lab.logger import lab_logger

        lab_logger.info('Cleaning CIMC {0}'.format(self))
        handle = ImcSdk.ImcHandle()
        try:
            handle.login(name=self._ipmi_ip, username=self._ipmp_username, password=self._ipmi_password)
            adapters = handle.get_imc_managedobject(None, 'adaptorHostEthIf', dump_xml='true')
            for adapter in adapters:
                if adapter.Name not in ['eth0', 'eth1']:
                    try:
                        handle.remove_imc_managedobject(in_mo=None, class_id=adapter.class_id, params={"Dn": adapter.Dn}, dump_xml='true')
                    except ImcSdk.ImcException as e:
                        lab_logger.info(e.error_descr)
            params = {'Dn': 'sys/rack-unit-1/bios/bios-settings/LOMPort-OptionROM', 'VpLOMPortsAllState': 'Enabled'}
            handle.set_imc_managedobject(None, class_id='BiosVfLOMPortOptionROM', params=params, dump_xml='true')
        finally:
            handle.logout()

    def cmd(self, cmd):
        return NotImplementedError

    def configure_for_osp7(self):
        import ImcSdk
        from lab.logger import lab_logger

        self.cleanup()
        lab_logger.info('Configuring CIMC in {0}'.format(self))
        handle = ImcSdk.ImcHandle()
        try:
            handle.login(name=self._ipmi_ip, username=self._ipmp_username, password=self._ipmi_password)
            params = {'Dn': 'sys/rack-unit-1/bios/bios-settings/LOMPort-OptionROM', 'VpLOMPortsAllState': 'Disabled'}
            handle.set_imc_managedobject(None, class_id='BiosVfLOMPortOptionROM', params=params, dump_xml='true')
            for wire in self._upstream_wires:
                params = dict()
                pci_slot_id, params["UplinkPort"] = wire.get_port_s().split('/')
                for nic_order, nic in enumerate(self.get_nics()):  # NIC order starts from 0
                    params["dn"] = "sys/rack-unit-1/adaptor-{pci_slot_id}/host-eth-{nic_name}".format(pci_slot_id=pci_slot_id, nic_name=nic.get_name())
                    if 'pxe' in nic.get_name():
                        params['PxeBoot'] = "enabled"
                    params['mac'] = nic.get_mac()
                    params['Name'] = nic.get_name()
                    if params['Name'] in ['eth0', 'eth1']:
                        handle.set_imc_managedobject(None,  'adaptorHostEthIf', params, dump_xml='true')
                    else:
                        handle.add_imc_managedobject(None,  'adaptorHostEthIf', params, dump_xml='true')
                    vlan = self.lab().get_net_vlans(nic.get_name())[0]  # Get the first VLAN of the net as a default VLAN
                    general_params = {"Dn": params['dn'] + '/general', ImcSdk.AdaptorEthGenProfile.VLAN: vlan, ImcSdk.AdaptorEthGenProfile.ORDER: nic_order}
                    handle.set_imc_managedobject(in_mo=None, class_id="AdaptorEthGenProfile", params=general_params)
        finally:
            handle.logout()
