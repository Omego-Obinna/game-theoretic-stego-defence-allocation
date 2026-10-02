"""Frozen-strategy catalogue sensitivity; never refits against expanded attacks."""
import gzip
import hashlib
import json
from pathlib import Path
import time
import numpy as np

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'fresh_seed_validation_v1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    started = time.perf_counter()
    meta = json.loads((HERE/'metadata.json').read_text())
    frozen = json.loads((PRIOR/'frozen_strategies.json').read_text())
    assert sha(PRIOR/'frozen_strategies.json') == meta['freeze_hash']
    assert sha(HERE/'session_results.json.gz') == meta['raw_hash']
    assert sha(HERE/'PLAN.md') == meta['plan_hash']
    with gzip.open(HERE/'session_results.json.gz', 'rt') as stream:
        raw = json.load(stream)
    lookup = {}
    for r in raw:
        key = tuple(r[k] for k in ('payload_bpp', 'environment', 'beta', 'pricing', 'seed', 'attack', 'policy'))
        assert key not in lookup
        lookup[key] = r
    attacks = meta['attack_catalogue']
    assert attacks[:5] == ['random', 'C1', 'C2', 'C3', 'burst']
    assert attacks[5:] == ['observe_C1', 'observe_C2', 'observe_C3', 'observe_best']
    seeds = frozen['seed_list']
    indices = np.random.default_rng(192999).integers(0, len(seeds), (2000, len(seeds)))
    results = []
    for game in frozen['games']:
        if game['environment'] == 'E0':
            continue
        p, env, beta, cap = [game[k] for k in ('payload_bpp', 'environment', 'beta', 'extra_byte_cap')]
        policies = game['policies']
        field = 'completion_rate' if game['endpoint'] == 'transport_completion' else 'recorded_extraction_weighted_rate'
        names = list(game['strategies'])
        weights = np.array([game['strategies'][name]['weights'] for name in names])
        for pricing in ('objects', 'bytes'):
            tensor = np.array([[[lookup[(p,env,beta,pricing,s,a,pol)][field] for a in attacks] for pol in policies] for s in seeds])
            cost_tensor = np.array([[lookup[(p,env,beta,pricing,s,attacks[0],pol)]['extra_fraction'] for pol in policies] for s in seeds])
            assert np.allclose(weights.sum(axis=1), 1) and np.min(weights) >= -1e-8
            for w in weights:
                assert np.all(cost_tensor[:,w>1e-8] <= cap+1e-8)
            per_seed = np.einsum('sij,ki->skj', tensor, weights)
            means = per_seed.mean(axis=0)
            boot = per_seed[indices].mean(axis=1)
            extended = means.min(axis=1)
            old = means[:,:5].min(axis=1)
            fixed = means[:,5:8].min(axis=1)
            adaptive = means[:,8]
            assert np.all(extended <= old+1e-12)
            boot_extended = boot.min(axis=2)
            boot_legacy = boot[:,:,:5].min(axis=2)
            boot_fixed = boot[:,:,5:8].min(axis=2)
            minimax = names.index('restricted_minimax')
            strategies = {}
            for k, name in enumerate(names):
                strategies[name] = {'per_attack_means': means[k].tolist(),
                    'legacy_catalogue_worst': float(old[k]), 'matched_fixed_reservation_worst': float(fixed[k]),
                    'adaptive_only': float(adaptive[k]), 'augmented_catalogue_worst': float(extended[k]),
                    'augmented_worst_attacks': [a for j,a in enumerate(attacks) if abs(means[k,j]-extended[k])<1e-12],
                    'legacy_to_augmented_drop': float(old[k]-extended[k]),
                    'legacy_to_augmented_drop_interval': np.quantile(boot_legacy[:,k]-boot_extended[:,k],[.025,.975]).tolist(),
                    'matched_fixed_minus_adaptive': float(fixed[k]-adaptive[k]),
                    'matched_fixed_minus_adaptive_interval': np.quantile(boot_fixed[:,k]-boot[:,k,8],[.025,.975]).tolist(),
                    'minimax_minus_this_augmented': float(extended[minimax]-extended[k]),
                    'minimax_minus_this_augmented_interval': np.quantile(boot_extended[:,minimax]-boot_extended[:,k],[.025,.975]).tolist(),
                    'expected_extra_fraction': float((cost_tensor@weights[k]).mean()),
                    'frozen_weights': weights[k].tolist(), 'per_seed_per_attack_expected_performance': per_seed[:,k].tolist()}
            coalitions = {}
            for s,c in game['coalitions'].items():
                w = np.zeros(len(policies))
                for pol,v in zip(c['policies'],c['weights']):
                    w[policies.index(pol)] = v
                assert np.all(cost_tensor[:,w>1e-8]<=cap+1e-8)
                scores = np.einsum('sij,i->sj',tensor,w).mean(axis=0)
                coalitions[s] = {'legacy_value': float(scores[:5].min()), 'adaptive_only':float(scores[8]), 'augmented_value':float(scores.min())}
            for s,c in coalitions.items():
                c['baseline_centred_augmented_value'] = c['augmented_value']-coalitions['0']['augmented_value']
            assert abs(coalitions['7']['augmented_value']-extended[minimax])<1e-8
            results.append({k:game[k] for k in ('endpoint','payload_bpp','environment','beta','extra_byte_cap','policies')} |
                {'pricing':pricing,'attacks':attacks,'strategies':strategies,'frozen_coalition_values':coalitions,'fitted_shapley_unchanged':game['fitted_shapley']})
    assert len(results)==288
    observation_rows = [r for r in raw if r['attack'].startswith('observe_')]
    assert all(r['learning_time_ms'] is None or r['learning_time_ms']>100 for r in observation_rows)
    assert all(r['final_reserved']==0 for r in raw)
    diagnostics = {'evaluated_configurations':len(results),'strategies_per_configuration':8,
        'frozen_weights_unchanged':True,'all_actual_hard_caps_verified':True,'augmented_minimum_never_exceeds_legacy':True,
        'learning_time_ms_range':[min(r['learning_time_ms'] for r in observation_rows if r['learning_time_ms'] is not None),max(r['learning_time_ms'] for r in observation_rows if r['learning_time_ms'] is not None)],
        'zero_final_reservations':True,'bootstrap_seed':192999,'bootstrap_resamples':2000,
        'wall_seconds':time.perf_counter()-started,'evaluator_hash':sha(__file__)}
    (HERE/'evaluated_strategies.json').write_text(json.dumps(results,indent=2)+'\n')
    diagnostics['results_hash']=sha(HERE/'evaluated_strategies.json')
    (HERE/'evaluation_diagnostics.json').write_text(json.dumps(diagnostics,indent=2)+'\n')
    print(json.dumps(diagnostics,indent=2))
    for r in results:
        if r['endpoint']=='transport_completion' and r['payload_bpp']==.2 and r['environment']=='E2' and r['beta']==.05 and r['extra_byte_cap'] in (.7,.85):
            print(json.dumps({'pricing':r['pricing'],'cap':r['extra_byte_cap'],'values':{n:{k:s[k] for k in ('legacy_catalogue_worst','matched_fixed_reservation_worst','adaptive_only','augmented_catalogue_worst')} for n,s in r['strategies'].items() if n in ('restricted_minimax','balanced_equal_repetition_probability','best_fixed_maximin','shapley_knapsack')}},indent=2))


if __name__=='__main__':
    main()
