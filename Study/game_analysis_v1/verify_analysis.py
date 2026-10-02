"""Independent arithmetic reconciliation of exported game solutions."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
results = json.loads((HERE / 'game_results.json').read_text())
diagnostics = json.loads((HERE / 'diagnostics.json').read_text())
for name, value in diagnostics['analysis_hashes'].items():
    assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == value
for name, value in diagnostics['source_hashes'].items():
    assert hashlib.sha256((HERE.parent / 'transport_pilot_v1' / name).read_bytes()).hexdigest() == value
empty_certificates = []
for r in results:
    matrix = r['payoff_matrix']
    value = r['noncooperative']['value']
    for name, c in r['comparators'].items():
        weights = c['weights']
        assert abs(sum(weights) - 1) < 1e-8 and min(weights) >= -1e-8
        payoffs = [sum(w * matrix[i][j] for i, w in enumerate(weights)) for j in range(5)]
        assert abs(min(payoffs) - c['worst_case']) < 1e-8
        assert c['worst_case'] <= value + 1e-8
        assert all(cost <= r['extra_byte_cap'] + 1e-8 for cost, w in zip(r['extra_costs'], weights) if w > 1e-8)
    coop = r['cooperative']
    worth = {int(s): v for s, v in coop['coalition_value'].items()}
    assert abs(sum(coop['shapley']) - worth[7]) < 1e-8
    if coop['core_nonempty']:
        allocation = coop['core_example']
        assert abs(sum(allocation) - worth[7]) < 1e-7
        assert all(sum(allocation[i] for i in range(3) if s & (1 << i)) >= worth[s] - 1e-7 for s in range(8))
    else:
        excess = sum(worth[s] for s in (1, 2, 4)) - worth[7]
        assert excess > 1e-8
        empty_certificates.append({'endpoint': r['endpoint'], 'payload_bpp': r['payload_bpp'],
            'environment': r['environment'], 'beta': r['beta'], 'cap': r['extra_byte_cap'],
            'singleton_sum_minus_grand_value': excess})
    if r['endpoint'] == 'transport_completion' and r['payload_bpp'] == .2 and r['environment'] == 'E2' and r['beta'] == .05:
        if r['extra_byte_cap'] == .7:
            assert abs(value - .8617583892617449) < 1e-8
        if r['extra_byte_cap'] == .85:
            assert abs(value - .8794260089686099) < 1e-8
summary = {'cells_reconciled': len(results), 'empty_core_certificates': empty_certificates,
           'unique_empty_core_conditions': len({(r['environment'], r['beta'], r['cap']) for r in empty_certificates}),
           'independent_representative_values_matched': True}
(HERE / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n')
print(f'{len(results)} cells reconciled; {len(empty_certificates)} empty-core certificates checked.')
