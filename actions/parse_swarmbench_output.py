#!/usr/bin/python3

import sys
import subprocess
from charms.docker import Docker
from charms.benchmark import Benchmark


def action_set(key, val):
    ''' Helper method to set key/val for benchmark data '''
    action_cmd = ['action-set']
    if isinstance(val, dict):
        for k, v in val.items():
            action_set('{}.{}'.format(key, k), v)
        return

    action_cmd.append('{}={}'.format(key, val))
    subprocess.check_call(action_cmd)


def parse_output(container_id):
    d = Docker()
    raw_logs = d.logs(container_id)

    run_output = raw_logs.splitlines()

    # The final 2 lines we care about have some specific strings
    # search for them and determine if it was actually a successful run

    # Time taken for tests: 27.048s
    # Time per container: 535.584ms [mean] | 1252.565ms [90th] | 2002.064ms [99th]  # noqa

    parsed = run_output[-1].replace('Time per container: ', '').split('|')

    print(parsed)

    mean = parsed[0].replace('ms [mean] ', '')
    ninety = parsed[1].replace('ms [90th] ', '')
    ninetynine = parsed[2].replace('ms [99th] ', '')

    total_parsed = run_output[-2].replace('Time taken for tests: ', '')
    total_time = total_parsed.replace('s', '')

    action_set(
        "results.total-time",
        {'value': total_time, 'units': 's'}
    )

    action_set(
        "results.mean-time",
        {'value': mean, 'units': 'ms'}
    )

    action_set(
        "results.90th-percentile",
        {'value': ninety, 'units': 'ms'}
    )

    action_set(
        "results.00th-percentile",
        {'value': ninetynine, 'units': 'ms'}
    )

    Benchmark.set_composite_score(
        total_time,
        'sec',
        'desc'
    )

if __name__ == "__main__":
    parse_output(sys.argv[1])
