"""Causal traffic-observation and serialized-byte suppression sensitivity."""
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
import sys

OUT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(OUT / 'transport_pilot_v1'))
from pilot import KEY, SESSION, REPRESENTATIVE, draw
from transport import Config, Receiver, emit

LEGACY = ('random', 'C1', 'C2', 'C3', 'burst')
OBSERVATION = ('observe_C1', 'observe_C2', 'observe_C3', 'observe_best')
ATTACKS = LEGACY + OBSERVATION


@dataclass(frozen=True)
class Observation:
    epoch: int
    channel: int
    copy: int
    send_ms: int
    serialized_bytes: int


class Budget:
    def __init__(self, beta, pricing, available, serialized_sizes):
        if pricing not in ('objects', 'bytes') or not 0 <= Fraction(str(beta)) <= 1:
            raise ValueError('Invalid budget')
        fraction = Fraction(str(beta))
        self.pricing, self.n = pricing, len(available)
        if not self.n or len(serialized_sizes) != 3 or min(serialized_sizes) <= 0:
            raise ValueError('Invalid workload')
        baseline = [3 if pricing == 'objects' else serialized_sizes[0] + serialized_sizes[1] + (serialized_sizes[2] if present else 0) for present in available]
        self.cap = int(fraction * sum(baseline))
        self.block_caps = {i // 100: int(fraction * sum(baseline[i:i+100])) for i in range(0, self.n, 100)}
        self.spent = self.reserved = 0
        self.block_spent = {b: 0 for b in self.block_caps}
        self.block_reserved = {b: 0 for b in self.block_caps}
        self.pending = {}
        self.max_reserved = 0

    def unit(self, observed):
        return 1 if self.pricing == 'objects' else observed.serialized_bytes

    def can(self, epoch, amount):
        block = epoch // 100
        return (0 <= epoch < self.n and amount >= 0 and
                self.spent + self.reserved + amount <= self.cap and
                self.block_spent[block] + self.block_reserved[block] + amount <= self.block_caps[block])

    def charge(self, observed):
        amount = self.unit(observed)
        if not self.can(observed.epoch, amount):
            return False
        self.spent += amount
        self.block_spent[observed.epoch // 100] += amount
        return True

    def reserve_set(self, observed, copies):
        key = (observed.epoch, observed.channel)
        if observed.copy != 0 or key in self.pending or copies not in (1, 2):
            raise ValueError('Invalid copy-set commitment')
        amount = self.unit(observed) * copies
        if not self.can(observed.epoch, amount):
            return False
        self.pending[key] = {'remaining': copies, 'unit': self.unit(observed), 'seen': set()}
        self.reserved += amount
        self.block_reserved[observed.epoch // 100] += amount
        self.max_reserved = max(self.max_reserved, self.reserved)
        return True

    def consume(self, observed):
        key = (observed.epoch, observed.channel)
        if key not in self.pending:
            return False
        entry = self.pending[key]
        if observed.copy in entry['seen'] or entry['unit'] != self.unit(observed):
            raise ValueError('Duplicate or wrong-sized committed transmission')
        entry['seen'].add(observed.copy)
        amount = entry['unit']
        self.reserved -= amount
        self.spent += amount
        self.block_reserved[observed.epoch // 100] -= amount
        self.block_spent[observed.epoch // 100] += amount
        entry['remaining'] -= 1
        if entry['remaining'] == 0:
            del self.pending[key]
        return True

    def finish(self):
        assert self.reserved == 0 and not self.pending
        assert self.spent <= self.cap
        assert all(self.block_reserved[b] == 0 and self.block_spent[b] <= self.block_caps[b] for b in self.block_caps)
        assert sum(self.block_spent.values()) == self.spent


class ObservedTarget:
    """No policy, future transmissions, receiver state or natural loss input."""
    def __init__(self, budget, forced_channel=None, offset=100):
        if forced_channel not in (None, 1, 2, 3):
            raise ValueError('Invalid fixed target')
        self.budget, self.forced_channel, self.offset = budget, forced_channel, offset
        self.probes, self.learned, self.sizes = {}, {}, {}
        self.target, self.learned_at_ms = None, None
        self.last_ms = -1
        self.seen = set()

    def decide(self, observed):
        o = observed
        identity = (o.epoch, o.channel, o.copy)
        if o.send_ms < self.last_ms or identity in self.seen:
            raise ValueError('Observation time reversal or duplicate')
        self.last_ms = o.send_ms
        self.seen.add(identity)
        if o.copy == 0 and o.channel not in self.probes:
            self.probes[o.channel] = {'epoch': o.epoch, 'time': o.send_ms, 'extra_seen': False}
            self.sizes[o.channel] = o.serialized_bytes
        probe = self.probes.get(o.channel)
        if probe and o.epoch == probe['epoch'] and o.copy == 1:
            probe['extra_seen'] = True
        for channel, p in self.probes.items():
            if channel not in self.learned and o.send_ms > p['time'] + self.offset:
                self.learned[channel] = int(p['extra_seen'])
        if self.target is None and len(self.learned) == 3:
            self.learned_at_ms = o.send_ms
            self.target = self.forced_channel or min((1, 2, 3), key=lambda ch: (
                (1 + self.learned[ch]) * (1 if self.budget.pricing == 'objects' else self.sizes[ch]), ch))
        if o.channel != self.target:
            return False
        if o.copy == 0:
            self.budget.reserve_set(o, 1 + self.learned[o.channel])
        return self.budget.consume(o)


def run(policy, seed, environment, attack, beta, pricing, available, serialized_sizes, objects=REPRESENTATIVE):
    if attack not in ATTACKS or environment not in ('E0', 'E1', 'E2'):
        raise ValueError('Unknown condition')
    n = len(available)
    config = Config(n)
    frames = [t for t in emit(KEY, SESSION, [objects] * n, policy, config) if t.channel != 3 or available[t.epoch]]
    budget = Budget(beta, pricing, available, serialized_sizes)
    learner = ObservedTarget(budget, None if attack == 'observe_best' else int(attack[-1])) if attack in OBSERVATION else None
    outages = set()
    if environment == 'E2':
        end = -1
        for boundary in range(n + 1):
            if boundary >= end and draw(seed, environment, 'outage', boundary) < .005:
                end = boundary + 3
                outages.update(range(boundary, end))
    receiver, events = Receiver(KEY, SESSION, config), []
    natural = suppressed_count = wasted = suppressed_bytes = 0
    for t in frames:
        observed = Observation(t.epoch, t.channel, t.copy, t.send_ms, serialized_sizes[t.channel - 1])
        if learner:
            suppressed = learner.decide(observed)
        else:
            start = (t.epoch // 100) * 100 + int(draw(seed, 'attack-burst-start', t.epoch // 100) * 100)
            selected = ((attack.startswith('C') and t.channel == int(attack[1])) or
                        (attack == 'random' and draw(seed, 'attack-random', t.epoch, t.channel, t.copy) < .25) or
                        (attack == 'burst' and t.epoch >= start))
            suppressed = budget.charge(observed) if selected else False
        # Observation/decision precedes impairment. Attacker never receives these draws.
        independent_loss = environment != 'E0' and draw(seed, environment, 'loss', t.epoch, t.channel, t.copy) < .01
        lost = independent_loss or t.send_ms // 100 in outages
        natural += int(lost)
        suppressed_count += int(suppressed)
        suppressed_bytes += observed.serialized_bytes if suppressed else 0
        wasted += int(lost and suppressed)
        jitter = {'E0': 0, 'E1': 50, 'E2': 100}[environment]
        delay = 20 + int(draw(seed, environment, 'base-delay', t.epoch, t.channel, t.copy) * 51)
        if jitter:
            delay += int(draw(seed, environment, 'jitter', t.epoch, t.channel, t.copy) * (jitter + 1))
        if not lost and not suppressed:
            events.append((t.send_ms + delay, t))
    for now, t in sorted(events, key=lambda x: (x[0], x[1].epoch, x[1].channel, x[1].copy)):
        receiver.receive(now, t.wire)
    outcomes = receiver.finalize()
    budget.finish()
    assert budget.spent == (suppressed_count if pricing == 'objects' else suppressed_bytes)
    complete = [e for e, r in outcomes.items() if r['outcome'] == 'complete']
    assert all(available[e] for e in complete)
    return {'completed_epochs': complete, 'latencies_ms': [outcomes[e]['latency_ms'] for e in complete],
        'emitted_objects': len(frames), 'natural_loss_objects': natural, 'suppressed_objects': suppressed_count,
        'suppressed_serialized_bytes': suppressed_bytes, 'wasted_suppressions': wasted, 'event_counts': receiver.counts,
        'attack_budget_unit': pricing, 'attack_cap': budget.cap, 'attack_spent': budget.spent,
        'attack_spent_per_block': budget.block_spent, 'attack_cap_per_block': budget.block_caps,
        'final_reserved': budget.reserved, 'maximum_reserved': budget.max_reserved,
        'observed_target': learner.target if learner else None,
        'learning_time_ms': learner.learned_at_ms if learner else None,
        'inferred_repetitions': learner.learned if learner else None}
