from lab.with_config import WithConfig
from lab.with_log import WithLogMixIn
from lab.laboratory import Laboratory


class FakeCloud(object):
    pod = Laboratory()


def starter(worker):
    return worker.start_worker_parallel()


class RunnerHA(WithConfig, WithLogMixIn):
    def __init__(self):
        from prettytable import PrettyTable

        self.table = PrettyTable()
        self.table.field_names = ['path', 'time', 'status', 'result', 'tims']
        self.cloud = None

    def __repr__(self):
        return u'RunnerHA'

    def execute_single_test(self, test_case):
        import multiprocessing
        import fabric.network
        import time

        test_case.time = time.time()  # used to calculate duration of test
        test_case.cloud = self.cloud
        manager = multiprocessing.Manager()
        status_dict = manager.dict()

        workers = test_case.workers
        for worker in workers:
            worker.cloud = self.cloud
            worker.status_dict = status_dict
            worker.set_status(worker.STATUS_CREATED)
            if not test_case.is_debug:
                worker.setup_worker()  # run all setup_worker in non-parallel
            else:
                worker.log('Setup...')

        fabric.network.disconnect_all()  # we do that since URL: http://stackoverflow.com/questions/29480850/paramiko-hangs-at-get-channel-while-using-multiprocessing
        time.sleep(2)

        pool = multiprocessing.Pool(len(workers))
        self.log('\n\n***AFTER THIS LINE PARALLEL EXECUTION STARTS***\n\n')
        results = pool.map(starter, workers)
        self.log('\n\n***PARALLEL EXECUTION FINISHED***\n\n')

        test_case.after_run(results=results, pretty_table=self.table)

        if not test_case.is_debug:
            map(lambda x: x.teardown_worker(), workers)  # run all teardown_workers

    def run(self, pod_name, test_regex, is_noclean, is_debug):
        import time
        from lab.elk import Elk

        available_tc = self.ls_configs(directory='ha')
        test_paths = sorted(filter(lambda x: test_regex in x, available_tc))

        if not test_paths:
            raise ValueError('Provided regexp "{}" does not match any tests'.format(test_regex))

        tests = self.create_tests(test_paths=test_paths, is_noclean=is_noclean, is_debug=is_debug)

        possible_drivers = set(reduce(lambda l,x: x.possible_drivers + l, tests, []))
        if len(test_paths) == 1 and test_paths[0] == 'dev01-test-parallel.yaml':  # special test case to test infrastructure itself, does not require cloud
            self.cloud = FakeCloud()
        else:
            self.cloud = self.init_cloud(pod_name=pod_name, possible_drivers=possible_drivers)

        start_time = time.time()
        map(lambda x: self.execute_single_test(test_case=x), tests)

        with self.open_artifact('main_results.txt', 'w') as f:
            f.write(self.table.get_string())

        if type(self.cloud) is not FakeCloud:
            elk = Elk(proxy=self.cloud.mediator)
            elk.filter_error_warning_in_last_seconds(seconds=time.time() - start_time)
            self.cloud.pod.r_collect_info(regex='error', comment=test_regex)
        print self.table

    @staticmethod
    def init_cloud(pod_name, possible_drivers):
        from lab.deployers.deployer_existing_cloud import DeployerExistingCloud

        deployer = DeployerExistingCloud(lab_name=pod_name, allowed_drivers=possible_drivers)
        cloud = deployer.execute({'clouds': [], 'servers': []})
        cloud.os_all()
        if len(cloud.computes) < 2:
            raise RuntimeError('{}: not possible to run on this cloud, number of compute hosts less then 2'.format(cloud))
        return cloud

    def create_tests(self, test_paths, is_noclean, is_debug):
        from lab.test_case import TestCase

        unique_id_seen = []
        test_cases = []
        for test_path in test_paths:
            test = TestCase(path=test_path, is_noclean=is_noclean, is_debug=is_debug, cloud=self.cloud)
            assert test.unique_id not in unique_id_seen
            unique_id_seen.append(test.unique_id)
            test_cases.append(test)

        return test_cases
