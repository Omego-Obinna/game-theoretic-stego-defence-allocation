"""Freeze existing strategies before new outcomes; no holdout data read."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
sys.path.insert(0, str(OUT / 'game_analysis_v1'))
from games import solve_zero_sum
import test_games


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if (HERE / 'frozen_strategies.json').exists():
        raise RuntimeError('Freeze already exists: inspect/reuse it; do not overwrite after holdout')
    if (HERE / 'session_results.json.gz').exists():
        raise RuntimeError('Holdout already present; cannot create a new freeze')
    tests = unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromModule(test_games))
    assert tests.wasSuccessful()
    source = OUT / 'game_analysis_v1/game_results.json'
    fitted = json.loads(source.read_text())
    frozen = []
    for row in fitted:
        matrix = row['payoff_matrix']
        coalitions = {}
        for s, policies in row['cooperative']['coalition_policies'].items():
            ix = [row['policies'].index(p) for p in policies]
            result = solve_zero_sum([matrix[i] for i in ix])
            assert abs(result['value'] - row['cooperative']['absolute_value'][s]) < 1e-8
            coalitions[s] = {'policies': policies, 'weights': result['x'], 'fitted_value': result['value']}
        # Use the originally frozen grand-coalition minimax weights, even if another
        # optimal LP solve could select a different equilibrium in a degenerate game.
        coalitions['7']['weights'] = row['noncooperative']['x']
        frozen.append({k: row[k] for k in ('endpoint', 'payload_bpp', 'environment', 'beta', 'extra_byte_cap', 'policies', 'attacks')} |
                      {'strategies': {name: {'weights': v['weights'], 'fitted_worst_case': v['worst_case']} for name, v in row['comparators'].items()},
                       'coalitions': coalitions, 'fitted_shapley': row['cooperative']['shapley']})
    value = {'freeze_scope': 'development outcomes only; immutable during holdout',
             'source_game_hash': sha(source), 'games_code_hash': sha(OUT / 'game_analysis_v1/games.py'),
             'pilot_code_hash': sha(OUT / 'transport_pilot_v1/pilot.py'),
             'transport_code_hash': sha(OUT / 'transport_validation_v1/transport.py'),
             'plan_hash': sha(HERE / 'PLAN.md'), 'freeze_code_hash': sha(__file__),
             'seed_list': list(range(191001, 191021)), 'bootstrap_seed': 191999,
             'bootstrap_resamples': 2000, 'games': frozen}
    (HERE / 'frozen_strategies.json').write_text(json.dumps(value, indent=2) + '\n')
    print('Frozen 216 game configurations and 1,728 coalition strategies before holdout.')


if __name__ == '__main__':
    main()
