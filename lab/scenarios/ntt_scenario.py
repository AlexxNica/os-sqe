from lab.parallelworker import ParallelWorker
from lab.decorators import section


class NttScenario(ParallelWorker):

    def check_config(self):
        possible_modes = ['csr', 'nfvbench', 'both']
        if self._what_to_run not in possible_modes:
            raise ValueError('{}: what-to-run must on of {}'.format(self, possible_modes))
        return 'run {}, # CSR {}, sleep {},  nfvbench {}'.format(self._what_to_run, self._csr_per_compute, self._csr_sleep, self._nfvbench_args)

    @property
    def _what_to_run(self):
        return self._kwargs['what-to-run']

    @property
    def _csr_per_compute(self):
        return self._kwargs['csr-per-compute']

    @property
    def _csr_sleep(self):
        return self._kwargs['csr-sleep']

    @property
    def _tmp_dir(self):
        return self._kwargs['tmp-dir']

    @property
    def _nfvbench_args(self):
        return self._kwargs['nfvbench-args'] + (' --no-cleanup' if self.is_noclean else '')

    @section(message='Setting up', estimated_time=100)
    def setup_worker(self):
        self._kwargs['tmp-dir'] = '/var/tmp/os-sqe-tmp/'

        self.get_mgmt().exe('rm -rf {}'.format(self._tmp_dir))
        self.get_mgmt().r_configure_mx_and_nat()
        if self._what_to_run in ['both', 'csr']:
            self.get_mgmt().r_clone_repo(repo_url='http://gitlab.cisco.com/openstack-perf/nfvi-test.git', local_repo_dir=self._tmp_dir + 'nfvi-test')
            self.get_mgmt().r_get_remote_file(url='http://172.29.173.233/cloud-images/csr1000v-universalk9.03.16.00.S.155-3.S-ext.qcow2', to_directory=self._tmp_dir + 'nfvi-test')
        if self._what_to_run in ['both', 'nfvbench']:
            self.get_mgmt().r_check_intel_nics()
            # self.get_lab().get_vtc()[0].vtc_create_nfvbench_tg()

        self.get_cloud().os_cleanup(is_all=True)
        self.get_cloud().os_quota_set()

    def loop_worker(self):
        if self._what_to_run in ['csr', 'both']:
            self.csr_run()

        if self._what_to_run in ['nfvbench', 'both']:
            self.nfvbench_run()

    def csr_run(self):

        n_csr = self._csr_per_compute if int(self._csr_per_compute) == 1 else int(self._csr_per_compute) * len(self.get_cloud().get_computes())
        cmd = 'source $HOME/openstack-configs/openrc && ./csr_create.sh  {} {} {}'.format(n_csr, self._csr_per_compute, self._csr_sleep)
        ans = self.get_mgmt().exe(cmd, in_directory=self._tmp_dir + 'nfvi-test')

        with self.get_lab().open_artifact('csr_create_output.txt', 'w') as f:
            f.write(cmd + '\n')
            f.write(ans)
        if 'ERROR' in ans:
            errors = [x.split('\r\n')[0] for x in ans.split('ERROR')[1:]]
            errors = [x for x in errors if 'No hypervisor matching' not in x]
            if errors:
                raise RuntimeError('# errors {} the first is {}'.format(len(errors), errors[0]))

    def nfvbench_run(self):
        cmd = 'nfvbench ' + self._nfvbench_args + ' --json results.json'
        ans = self.get_mgmt().exe(cmd, is_warn_only=True)
        with self.get_lab().open_artifact('nfvbench_output_{}.txt'.format(self._nfvbench_args.replace(' ', '_')), 'w') as f:
            f.write(cmd + '\n')
            f.write(ans)

        if 'ERROR' in ans:
            raise RuntimeError(ans.split('ERROR')[1][:200])
        else:
            res_json_body = self.get_mgmt().r_get_file_from_dir(file_name='results.json')
            self.process_nfvbench_json(res_json_body=res_json_body)

    def process_nfvbench_json(self, res_json_body):
        import json

        j = json.loads(res_json_body)

        with self.get_lab().open_artifact('{}-{}-{}-{}.json'.format(j['openstack_spec']['vswitch'], j['config']['service_chain'], j['config']['service_chain_count'], j['config']['flow_count']), 'w') as f:
            f.write(res_json_body)

        res = []
        for mtu, di in j['benchmarks']['network']['service_chain'][j['config']['service_chain']]['result']['result'].items():
            if 'ndr' in di:
                for t in ['ndr', 'pdr']:
                    la_min, la_avg, la_max = di[t]['stats']['overall']['min_delay_usec'], di[t]['stats']['overall']['avg_delay_usec'], di[t]['stats']['overall']['max_delay_usec']
                    gbps = di[t]['rate_bps'] / 1e9
                    drop_thr = di[t]['stats']['overall']['drop_percentage']
                    res.append('MTU={} {}({:.4f}) rate={:.4f} Gbps latency={:.1f} {:.1f} {:.1f} usec'.format(mtu, t, drop_thr, gbps, la_min, la_avg, la_max))
            else:
                res.append('MTU={} RT={}'.format(mtu, di['stats']['overall']['rx']['pkt_bit_rate'] + di['stats']['overall']['tx']['pkt_bit_rate']))

        with self.get_lab().open_artifact('main-results-for-tims.txt'.format(), 'w') as f:
            f.write(self._nfvbench_args + '\n' + '; '.join(res))

    @section(message='Tearing down', estimated_time=30)
    def teardown_worker(self):
        if not self.is_noclean:
            self.get_cloud().os_cleanup()
            self.get_mgmt().exe('rm -rf ' + self._tmp_dir)

"""
#!/bin/bash

# Script runs nfvbench tool with all necessary parameters.
# It runs from current working directory. To run nfvbench in this directory:
#   1. copy cfg.default.yaml (run this script with --show-config and redirect output to file)
#       nfvbench.sh --show-config > nfvbench.cfg
#   2. keep defaults for paths to OpenStack files (default is /tmp/nfvbench/openstack)

SPIRENT_CONTAINER="cloud-docker.cisco.com/spirent"
NFVBENCH_CONTAINER="cloud-docker.cisco.com/nfvbench"

if [ -d "/root/openstack-configs" ]; then
    EXTRA_ARGS="-v /root/openstack-configs:/tmp/nfvbench/openstack"
else
    EXTRA_ARGS=""
fi

SPIRENT_COMMAND="docker run --privileged --net host -td ${SPIRENT_CONTAINER}"
SPIRENT_CONTAINER_ID="$($SPIRENT_COMMAND)"

KERNEL=$(uname -r)

NFVBENCH_COMMAND="docker run \
    --rm \
    --privileged \
    --net host \
    -it \
    --volumes-from ${SPIRENT_CONTAINER_ID} \
    -v ${PWD}:/tmp/nfvbench \
    -v /etc/hosts:/etc/hosts \
    -v ${HOME}/.ssh:/root/.ssh \
    -v /dev:/dev \
    -v /lib/modules/${KERNEL}:/lib/modules/${KERNEL} \
    -v /usr/src/kernels/${KERNEL}:/usr/src/kernels/${KERNEL} \
    ${EXTRA_ARGS} \
    ${NFVBENCH_CONTAINER} nfvbench"

$NFVBENCH_COMMAND $*

docker rm -f $SPIRENT_CONTAINER_ID

lsmod | grep igb_uio
cd /opt/trex/v2.18
./t-rex-64 -i --no-scapy-server
cat /tmp/trex

"""