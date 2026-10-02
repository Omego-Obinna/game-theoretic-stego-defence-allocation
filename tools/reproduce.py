"""Reproduce in a new working copy, never in the recorded study directory."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def compare(a, b, trail='root'):
    if isinstance(a, dict):
        if not isinstance(b, dict) or a.keys() != b.keys():
            raise AssertionError(f'Dictionary mismatch: {trail}')
        return max([compare(a[k], b[k], trail+'.'+k) for k in a] or [0.0])
    if isinstance(a, list):
        if not isinstance(b, list) or len(a) != len(b):
            raise AssertionError(f'List mismatch: {trail}')
        return max([compare(x, y, f'{trail}[{i}]') for i, (x, y) in enumerate(zip(a,b))] or [0.0])
    if isinstance(a, (int, float)) and not isinstance(a, bool):
        if not isinstance(b, (int, float)) or isinstance(b, bool):
            raise AssertionError(f'Numeric type mismatch: {trail}')
        if not math.isclose(a, b, rel_tol=0, abs_tol=1e-10):
            raise AssertionError(f'Numerical mismatch: {trail}: {a} versus {b}')
        return abs(a-b)
    if a != b:
        raise AssertionError(f'Value mismatch: {trail}')
    return 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', choices=['check', 'analysis', 'figures'])
    args = parser.parse_args()
    subprocess.run([sys.executable, str(ROOT/'tools/check_integrity.py')], check=True)
    parent = ROOT/'reproduced'
    parent.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=args.task+'-', dir=parent))
    shutil.copytree(ROOT/'study', work/'study', ignore=shutil.ignore_patterns('__pycache__','tmp','output','figures'))
    logdir = work/'logs'
    logdir.mkdir()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', MPLCONFIGDIR=str(work/'matplotlib-cache'))
    report = {'task': args.task, 'reference_files_modified': False, 'new_full_simulation_sweep': False,
              'commands': [], 'comparisons': [], 'passed': False}
    start = time.perf_counter()

    def run(stage, *arguments):
        name = f'{len(report["commands"])+1:02d}_{stage}_{arguments[-1].replace("/", "_")}.txt'
        print(f'Running {stage}: {" ".join(arguments)}', flush=True)
        with (logdir/name).open('w') as log:
            result = subprocess.run([sys.executable, *arguments], cwd=work/'study'/stage,
                                    env=env, stdout=log, stderr=subprocess.STDOUT)
        report['commands'].append({'stage':stage, 'arguments':list(arguments), 'returncode':result.returncode,
                                   'log':'logs/'+name})
        if result.returncode:
            raise RuntimeError(f'Failed: {stage}; inspect {logdir/name}')

    try:
        if args.task == 'check':
            run('transport_validation_v1', '-m', 'unittest', '-v', 'test_transport')
            run('game_analysis_v1', '-m', 'unittest', '-v', 'test_games')
            run('transport_sensitivity_v1', '-m', 'unittest', '-v', 'test_engine')
            run('game_analysis_v1', 'verify_analysis.py')
            run('fresh_seed_validation_v1', 'verify.py')
            run('transport_sensitivity_v1', 'verify.py')
            run('transport_sensitivity_v1', 'verify_bootstrap.py')
        elif args.task == 'analysis':
            for stage, script, result in [
                ('game_analysis_v1','analyse.py','game_results.json'),
                ('fresh_seed_validation_v1','evaluate.py','evaluated_strategies.json'),
                ('transport_sensitivity_v1','evaluate.py','evaluated_strategies.json')]:
                run(stage, script)
                original = (ROOT/'study'/stage/result).read_bytes()
                reproduced = (work/'study'/stage/result).read_bytes()
                error = compare(json.loads(original), json.loads(reproduced))
                report['comparisons'].append({'path':stage+'/'+result,'max_absolute_numeric_difference':error,
                    'byte_identical':original==reproduced,
                    'original_sha256':hashlib.sha256(original).hexdigest(),
                    'reproduced_sha256':hashlib.sha256(reproduced).hexdigest()})
        else:
            run('manuscript_results_v1', 'build_figures.py')
            run('manuscript_rebalanced_v1', 'build_promoted_figures.py')
        report['passed'] = True
    finally:
        report['elapsed_seconds'] = time.perf_counter()-start
        (work/'run_report.json').write_text(json.dumps(report,indent=2)+'\n')
        print('Report: '+str(work.relative_to(ROOT)/'run_report.json'), flush=True)
    subprocess.run([sys.executable,str(ROOT/'tools/check_integrity.py')],check=True)


if __name__ == '__main__':
    main()
