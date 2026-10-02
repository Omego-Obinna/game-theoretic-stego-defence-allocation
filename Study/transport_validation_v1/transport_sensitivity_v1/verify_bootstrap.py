"""Check representative interval arithmetic using resampling-count matrices."""
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent


def percentile(values, q):
    ordered = sorted(values)
    position = (len(ordered)-1)*q
    low = int(position)
    return ordered[low] + (position-low)*(ordered[min(low+1, len(ordered)-1)]-ordered[low])


def main():
    frozen = json.loads((HERE.parent/'fresh_seed_validation_v1/frozen_strategies.json').read_text())
    results = json.loads((HERE/'evaluated_strategies.json').read_text())
    with gzip.open(HERE/'session_results.json.gz', 'rt') as stream:
        raw = json.load(stream)
    lookup = {tuple(r[k] for k in ('pricing','seed','payload_bpp','environment','beta','attack','policy')):r for r in raw}
    key = lambda r: tuple(r[k] for k in ('endpoint','payload_bpp','environment','beta','extra_byte_cap'))
    games = {key(g):g for g in frozen['games']}
    rng = np.random.default_rng(192999)
    counts = np.array([np.bincount(rng.integers(0,20,20), minlength=20) for _ in range(2000)])
    checked, maximum_error = 0, 0.0
    for r in results:
        if not (r['endpoint']=='transport_completion' and r['payload_bpp']==.2 and r['environment']=='E2'
                and r['beta']==.05 and r['extra_byte_cap'] in (.7,.85)):
            continue
        game = games[key(r)]
        bootstraps = {}
        for name, strategy in game['strategies'].items():
            rows = []
            for seed in frozen['seed_list']:
                rows.append([sum(weight*lookup[(r['pricing'],seed,.2,'E2',.05,attack,pol)]['completion_rate']
                                 for pol,weight in zip(game['policies'],strategy['weights'])) for attack in r['attacks']])
            bootstraps[name] = counts @ np.array(rows) / 20
        minimax = bootstraps['restricted_minimax'].min(axis=1)
        for name, means in bootstraps.items():
            extended = means.min(axis=1)
            series = {
                'legacy_to_augmented_drop_interval': means[:,:5].min(axis=1)-extended,
                'matched_fixed_minus_adaptive_interval': means[:,5:8].min(axis=1)-means[:,8],
                'minimax_minus_this_augmented_interval': minimax-extended,
            }
            for field, values in series.items():
                for q, saved in zip((.025,.975), r['strategies'][name][field]):
                    error = abs(float(percentile(values,q))-saved)
                    maximum_error = max(maximum_error,error)
                    assert error < 1e-12
                    checked += 1
    assert checked == 192
    report = {'passed': True, 'representative_configurations': 4, 'interval_endpoints_checked': checked,
              'max_absolute_error': maximum_error,
              'scope': 'Arithmetic verification only; does not establish statistical coverage, significance or equivalence.',
              'verifier_hash':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (HERE/'bootstrap_verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
