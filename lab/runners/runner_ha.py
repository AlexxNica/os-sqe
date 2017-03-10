from lab.base_lab import LabWorker


def starter(worker):
    return worker.start_worker()


class RunnerHA(LabWorker):
    MODE_CHECK = 'check'
    MODE_RUN = 'run'
    MODE_DEBUG = 'debug'

    @staticmethod
    def sample_config():
        return {'task-yaml': 'task-ha.yaml', 'mode': 'run'}

    def __init__(self, config):
        self._task_yaml_path = config['task-yaml']
        self._task_body = self.read_config_from_file(config_path=self._task_yaml_path, directory='ha')
        self._mode = config['mode']

        if not self._task_body:
            raise Exception('Empty Test task list. Please check the file: {0}'.format(self._task_yaml_path))

    def execute(self, cloud):
        import importlib
        import multiprocessing
        import fabric.network
        import time

        manager = multiprocessing.Manager()
        status_dict = manager.dict()

        common_args = {'cloud': cloud, 'lab': cloud.get_lab(), 'yaml-path': self._task_yaml_path, 'is-debug': self._mode == self.MODE_DEBUG}

        names_already_seen = []
        for desc in self._task_body:  # first path to check that all workers have unique names
            if 'class' not in desc:
                continue
            try:
                name = desc['name']
            except KeyError:
                raise ValueError('{} in {} should define "name"'.format(desc['class'], self._task_yaml_path))
            if name in names_already_seen:
                raise ValueError('{} in {} defines name "{}" which is already defined somewhere else'.format(desc['class'], self._task_yaml_path, name))
            status_dict[name] = 'before init'

        workers = []
        for desc in self._task_body:  # second path to init all workers
            if 'class' not in desc:
                continue
            path_to_module, class_name = desc['class'].rsplit('.', 1)
            try:
                module = importlib.import_module(path_to_module)
            except ImportError:
                raise ValueError('{}: tries to run {}.py which does not exist'.format(self._task_yaml_path, path_to_module))
            try:
                klass = getattr(module, class_name)
            except AttributeError:
                raise ValueError('Please create class {} in {}.py'.format(class_name, path_to_module))
            desc.update(common_args)
            workers.append(klass(status_dict=status_dict, args_dict=desc))

        if self._mode == self.MODE_CHECK:
            return []
        fabric.network.disconnect_all()  # we do that since URL: http://stackoverflow.com/questions/29480850/paramiko-hangs-at-get-channel-while-using-multiprocessing
        time.sleep(2)

        pool = multiprocessing.Pool(len(workers))
        return pool.map(starter, workers)

    @staticmethod
    def run(lab_cfg_path, test_regex, mode):
        import time
        from lab.deployers.deployer_existing import DeployerExisting
        from lab.tims import Tims
        from lab.elk import Elk

        available_tc = RunnerHA.ls_configs(directory='ha')
        tests = sorted(filter(lambda x: test_regex in x, available_tc))

        if not tests:
            raise ValueError('Provided regexp "{}" does not match any tests'.format(test_regex))

        RunnerHA.check_config(tests)

        deployer = DeployerExisting(config={'hardware-lab-config': lab_cfg_path})
        cloud = deployer.execute([])
        if len(cloud.get_computes()) < 2:
            raise RuntimeError('{}: not possible to run on this cloud, number of compute hosts less then 2'.format(lab_cfg_path))

        mercury_version, vts_version = cloud.get_lab().r_get_version()

        tims = Tims()
        exceptions = []

        for tst in tests:
            start_time = time.time()
            runner = RunnerHA(config={'task-yaml': tst, 'mode': mode})
            results = runner.execute(cloud)

            elk = Elk(proxy=cloud.get_mediator())
            elk.filter_error_warning_in_last_seconds(seconds=time.time() - start_time)
            tims.publish_result(test_cfg_path=tst, mercury_version=mercury_version, lab=cloud.get_lab(), results=results)
            exceptions = reduce(lambda l, x: l + x['exceptions'], results, exceptions)

        cloud.get_lab().r_collect_information(regex='error', comment=test_regex)

        if exceptions:
            raise RuntimeError('Possible reason: {}'.format(exceptions))

    @staticmethod
    def check_config(tests):

        class FakeCloud(object):
            @staticmethod
            def get_lab():
                return 'fake_lab'

        cloud = FakeCloud()

        for tst in tests:
            r = RunnerHA(config={'task-yaml': tst, 'mode': RunnerHA.MODE_CHECK})
            r.execute(cloud=cloud)
