"""CPU-only, application-object validation model; not a stego decoder/network stack."""
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import hmac
import itertools
import struct

MAGIC = b'GTV1'
HEADER = struct.Struct('>4s16sQBII32s32s')
TAG_BYTES = 32
ENVELOPE_BYTES = HEADER.size + TAG_BYTES
PROFILE = hashlib.sha256(b'GTV1|required-C1-C2-C3|full-files|no-ECC|no-checkpoints').digest()


def transcript_hash(objects):
    if len(objects) != 3:
        raise ValueError('Exactly three objects required')
    digest = hashlib.sha256(b'GTV1-transcript')
    for channel, payload in enumerate(objects, 1):
        digest.update(struct.pack('>BQ', channel, len(payload)))
        digest.update(payload)
    return digest.digest()


def encode(key, session, epoch, channel, copy, payload, root, profile=PROFILE):
    if len(key) < 32 or len(session) != 16 or len(root) != 32 or len(profile) != 32:
        raise ValueError('Invalid key or context length')
    if channel not in (1, 2, 3) or copy not in (0, 1):
        raise ValueError('Unsupported channel or copy')
    header = HEADER.pack(MAGIC, session, epoch, channel, copy, len(payload), profile, root)
    body = header + payload
    return body + hmac.digest(key, body, 'sha256')


def decode(key, wire):
    if len(wire) < ENVELOPE_BYTES:
        raise ValueError('malformed')
    magic, session, epoch, channel, copy, length, profile, root = HEADER.unpack(wire[:HEADER.size])
    if magic != MAGIC or channel not in (1, 2, 3) or copy not in (0, 1) or len(wire) != length + ENVELOPE_BYTES:
        raise ValueError('malformed')
    if not hmac.compare_digest(wire[-TAG_BYTES:], hmac.digest(key, wire[:-TAG_BYTES], 'sha256')):
        raise ValueError('authentication')
    return session, epoch, channel, copy, profile, root, wire[HEADER.size:-TAG_BYTES]


@dataclass(frozen=True)
class Config:
    epochs: int
    interval_ms: int = 100
    deadline_ms: int = 500
    window: int = 10
    spread_ms: int = 300
    copy_offset_ms: int = 100

    def __post_init__(self):
        if self.epochs < 1 or self.interval_ms <= 0 or self.deadline_ms < 0 or self.window < 1 or self.spread_ms < 0 or self.copy_offset_ms < 0:
            raise ValueError('Invalid timing configuration')

    def release(self, epoch):
        return epoch * self.interval_ms

    def deadline(self, epoch):
        return self.release(epoch) + self.deadline_ms


@dataclass(frozen=True)
class Transmission:
    epoch: int
    channel: int
    copy: int
    send_ms: int
    wire: bytes


def emit(key, session, bundles, policy, config):
    """All originals and proactive copies are emitted without receiver feedback."""
    if len(bundles) != config.epochs or len(policy) != 3 or any(r not in (0, 1) for r in policy):
        raise ValueError('Invalid workload/policy')
    result = []
    for epoch, objects in enumerate(bundles):
        root = transcript_hash(objects)
        for channel, payload in enumerate(objects, 1):
            for copy in range(policy[channel - 1] + 1):
                result.append(Transmission(epoch, channel, copy,
                    config.release(epoch) + copy * config.copy_offset_ms,
                    encode(key, session, epoch, channel, copy, payload, root)))
    return sorted(result, key=lambda t: (t.send_ms, t.epoch, t.channel, t.copy))


def costs(object_sizes, policy):
    if len(object_sizes) != 3 or len(policy) != 3 or any(r not in (0, 1) for r in policy) or any(n < 0 for n in object_sizes):
        raise ValueError('Invalid costs input')
    per_channel = [size + ENVELOPE_BYTES for size in object_sizes]
    base = sum(per_channel)
    extra = sum(n * r for n, r in zip(per_channel, policy))
    return {'base_bytes': base, 'extra_bytes': extra, 'total_bytes': base + extra,
            'per_channel_bytes': per_channel, 'extra_fraction': extra / base}


def feasible(object_sizes, policy, extra_cap):
    c = costs(object_sizes, policy)
    return Fraction(c['extra_bytes'], c['base_bytes']) <= Fraction(str(extra_cap))


POLICIES = tuple(itertools.product((0, 1), repeat=3))


class Receiver:
    """Knows schedule/key/context only, never sender payload ground truth.

    Clock-driven window starts at the oldest not-yet-expired scheduled epoch.
    Arrival at the exact deadline is on time. No post-horizon late recovery.
    """
    def __init__(self, key, session, config, profile=PROFILE):
        self.key, self.session, self.config, self.profile = key, session, config, profile
        self.buffers, self.results, self.counts = {}, {}, {}
        self.now, self.closed = -1, False
        self.next_expiry = 0

    def count(self, name):
        self.counts[name] = self.counts.get(name, 0) + 1

    def expire(self, now, inclusive=False):
        while self.next_expiry < self.config.epochs:
            epoch = self.next_expiry
            deadline = self.config.deadline(epoch)
            if not (deadline < now or (inclusive and deadline == now)):
                break
            if epoch not in self.results:
                self.results[epoch] = {'outcome': 'expired', 'completion_ms': None}
                self.buffers.pop(epoch, None)
            self.next_expiry += 1

    def receive(self, now, wire):
        if self.closed or now < self.now or now < 0:
            raise ValueError('Closed receiver or nonmonotone clock')
        self.now = now
        self.expire(now)
        try:
            session, epoch, channel, copy, profile, root, payload = decode(self.key, wire)
        except ValueError as error:
            self.count(str(error))
            return
        if session != self.session or profile != self.profile:
            self.count('wrong_context')
            return
        if epoch >= self.config.epochs:
            self.count('unknown_epoch')
            return
        if epoch in self.results:
            self.count('post_completion_duplicate' if self.results[epoch]['outcome'] == 'complete' else 'late')
            return
        if now < self.config.release(epoch):
            self.count('before_release')
            return
        # Integer expression for ceil((now - deadline_duration) / interval).
        left = max(0, (now - self.config.deadline_ms + self.config.interval_ms - 1) // self.config.interval_ms)
        if epoch >= left + self.config.window:
            self.count('out_of_window')
            return
        buffer = self.buffers.setdefault(epoch, {'root': root, 'objects': {}, 'times': {}})
        if buffer['root'] != root:
            self.count('transcript_conflict')
            return
        if channel in buffer['objects']:
            if buffer['objects'][channel] != payload:
                self.count('object_conflict')
                return
            self.count('valid_duplicate')
        buffer['objects'][channel] = payload
        buffer['times'][channel] = now
        if len(buffer['objects']) == 3:
            objects = tuple(buffer['objects'][ch] for ch in (1, 2, 3))
            if transcript_hash(objects) != root:
                self.count('transcript_hash_failure')
                return
            times = buffer['times'].values()
            if max(times) - min(times) > self.config.spread_ms:
                self.count('spread_exceeded')
                return
            self.results[epoch] = {'outcome': 'complete', 'completion_ms': now,
                                   'latency_ms': now - self.config.release(epoch),
                                   'object_hashes': [hashlib.sha256(p).hexdigest() for p in objects]}
            del self.buffers[epoch]

    def finalize(self):
        self.expire(self.config.deadline(self.config.epochs - 1), inclusive=True)
        self.closed = True
        assert len(self.results) == self.config.epochs
        return dict(sorted(self.results.items()))


class SuppressionBudget:
    """Causal object-priced ledger, fixed baseline denominator; no carry-over."""
    def __init__(self, epochs, beta, block_epochs=100):
        self.beta = Fraction(str(beta))
        if epochs < 1 or not 0 <= self.beta <= 1 or block_epochs < 1:
            raise ValueError('Invalid attacker budget')
        self.epochs, self.block_epochs = epochs, block_epochs
        self.cap = int(self.beta * 3 * epochs)
        self.spent, self.blocks, self.seen = 0, {}, set()
        self.last_send = -1

    def decide(self, transmission, target_channel=None):
        """Receives current emission only; no future impairments/receiver state."""
        t = transmission
        if t.send_ms < self.last_send or not 0 <= t.epoch < self.epochs or target_channel not in (None, 1, 2, 3):
            raise ValueError('Invalid causal attack input')
        identity = (t.epoch, t.channel, t.copy)
        if identity in self.seen:
            raise ValueError('Transmission presented to attacker twice')
        self.seen.add(identity)
        self.last_send = t.send_ms
        block = t.epoch // self.block_epochs
        n = min(self.block_epochs, self.epochs - block * self.block_epochs)
        block_cap = int(self.beta * 3 * n)
        if target_channel is not None and t.channel != target_channel:
            return False
        if self.spent >= self.cap or self.blocks.get(block, 0) >= block_cap:
            return False
        self.spent += 1
        self.blocks[block] = self.blocks.get(block, 0) + 1
        return True


def simulate(key, session, bundles, policy, config, delay_ms=20, natural_drop=lambda t: False, attacker=None, target_channel=None):
    """Deterministic validation harness; not a calibrated network model."""
    if delay_ms < 0:
        raise ValueError('Negative delay')
    transmissions = emit(key, session, bundles, policy, config)
    receiver = Receiver(key, session, config)
    events, suppressed, natural, wasted = [], 0, 0, 0
    for t in transmissions:
        attacked = attacker.decide(t, target_channel) if attacker else False
        # Natural loss is evaluated after the attack decision, never exposed to it.
        lost = bool(natural_drop(t))
        suppressed += attacked
        natural += lost
        wasted += attacked and lost
        if not attacked and not lost:
            events.append((t.send_ms + delay_ms, t))
    for now, t in sorted(events, key=lambda item: (item[0], item[1].epoch, item[1].channel, item[1].copy)):
        receiver.receive(now, t.wire)
    outcomes = receiver.finalize()
    return {'outcomes': outcomes, 'event_counts': receiver.counts,
            'emitted_bytes': sum(len(t.wire) for t in transmissions),
            'emitted_objects': len(transmissions), 'suppressed_objects': suppressed,
            'natural_loss_objects': natural, 'wasted_suppressions': wasted}


def extraction_weighted_completion(outcomes, recorded_success):
    """An archived masked-bit indicator, NOT newly measured message recovery."""
    if set(outcomes) != set(recorded_success) or any(v not in (0, 1) for v in recorded_success.values()):
        raise ValueError('Every offered epoch needs its original success/failure flag')
    return sum(row['outcome'] == 'complete' and recorded_success[e] == 1 for e, row in outcomes.items())
