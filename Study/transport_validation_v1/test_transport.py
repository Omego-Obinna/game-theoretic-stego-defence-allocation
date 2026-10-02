import hashlib
import itertools
import unittest
from dataclasses import replace
from transport import (Config, Receiver, SuppressionBudget, emit, simulate, encode,
                       decode, transcript_hash, costs, feasible, POLICIES,
                       ENVELOPE_BYTES, HEADER, PROFILE, extraction_weighted_completion)

KEY = b'validation-only-not-a-deployment-key'
SESSION = b'validation000001'
OBJECTS = (b'gamma-one', b'gamma-two', b'saved-stego-object')


class TransportTests(unittest.TestCase):
    def wires(self, config=None, objects=OBJECTS, policy=(0, 0, 0)):
        config = config or Config(1)
        return emit(KEY, SESSION, [objects] * config.epochs, policy, config)

    def test_wire_round_trip_and_exact_size(self):
        for t in self.wires():
            self.assertEqual(decode(KEY, t.wire)[-1], OBJECTS[t.channel - 1])
            self.assertEqual(len(t.wire), len(OBJECTS[t.channel - 1]) + ENVELOPE_BYTES)
        self.assertEqual(ENVELOPE_BYTES, 133)

    def test_objects_longer_than_digest_are_not_truncated(self):
        objects = (b'a' * 64, b'b' * 257, bytes(range(256)) * 8)
        for t in self.wires(objects=objects):
            self.assertEqual(decode(KEY, t.wire)[-1], objects[t.channel - 1])

    def test_valid_copy_after_invalid_original(self):
        receiver = Receiver(KEY, SESSION, Config(1))
        for t in self.wires(policy=(1, 0, 0)):
            wire = bytearray(t.wire)
            if t.channel == 1 and t.copy == 0:
                wire[HEADER.size] ^= 1
            receiver.receive(t.send_ms + 20, bytes(wire))
        self.assertEqual(receiver.finalize()[0]['outcome'], 'complete')
        self.assertEqual(receiver.counts['authentication'], 1)

    def test_clock_window_advances_after_unseen_epoch_expires(self):
        receiver = Receiver(KEY, SESSION, Config(2, window=1))
        for t in self.wires(Config(2)):
            if t.epoch == 1:
                receiver.receive(501, t.wire)
        self.assertEqual(receiver.finalize()[0]['outcome'], 'expired')
        self.assertEqual(receiver.results[1]['outcome'], 'complete')

    def test_repeated_finalization_does_not_duplicate_outcomes(self):
        receiver = Receiver(KEY, SESSION, Config(2))
        self.assertEqual(receiver.finalize(), receiver.finalize())
        self.assertEqual(len(receiver.results), 2)

    def test_all_arrival_permutations_complete(self):
        for order in itertools.permutations(self.wires()):
            receiver = Receiver(KEY, SESSION, Config(1))
            for t in order:
                receiver.receive(20, t.wire)
            result = receiver.finalize()[0]
            self.assertEqual(result['outcome'], 'complete')
            self.assertEqual(result['object_hashes'], [hashlib.sha256(p).hexdigest() for p in OBJECTS])

    def test_missing_each_required_channel_expires(self):
        for channel in (1, 2, 3):
            result = simulate(KEY, SESSION, [OBJECTS], (0, 0, 0), Config(1), natural_drop=lambda t: t.channel == channel)
            self.assertEqual(result['outcomes'][0]['outcome'], 'expired')

    def test_completely_lost_epochs_in_denominator(self):
        result = simulate(KEY, SESSION, [OBJECTS] * 7, (0, 0, 0), Config(7), natural_drop=lambda t: True)
        self.assertEqual(len(result['outcomes']), 7)
        self.assertTrue(all(v['outcome'] == 'expired' for v in result['outcomes'].values()))

    def test_all_channels_payload_tampering_rejected(self):
        for bad_channel in (1, 2, 3):
            receiver = Receiver(KEY, SESSION, Config(1))
            for t in self.wires():
                wire = bytearray(t.wire)
                if t.channel == bad_channel:
                    wire[HEADER.size] ^= 1
                receiver.receive(20, bytes(wire))
            self.assertEqual(receiver.finalize()[0]['outcome'], 'expired')
            self.assertEqual(receiver.counts['authentication'], 1)

    def test_header_tampering_rejected(self):
        for index in (4, 20, 29, 37, 69):
            wire = bytearray(self.wires()[0].wire)
            wire[index] ^= 1
            with self.assertRaises(ValueError):
                decode(KEY, bytes(wire))

    def test_malformed_length_and_truncated_input(self):
        wire = self.wires()[0].wire
        for invalid in (b'', wire[:10], wire[:-1], wire + b'x'):
            with self.assertRaises(ValueError):
                decode(KEY, invalid)

    def test_wrong_key_rejected(self):
        with self.assertRaises(ValueError):
            decode(b'z' * 32, self.wires()[0].wire)

    def test_wrong_session_or_configuration_rejected(self):
        for session, profile in ((b'x' * 16, PROFILE), (SESSION, b'x' * 32)):
            receiver = Receiver(KEY, SESSION, Config(1))
            wire = encode(KEY, session, 0, 1, 0, OBJECTS[0], transcript_hash(OBJECTS), profile)
            receiver.receive(10, wire)
            self.assertEqual(receiver.counts['wrong_context'], 1)
            self.assertFalse(receiver.buffers)

    def test_cross_epoch_components_do_not_complete(self):
        receiver = Receiver(KEY, SESSION, Config(2))
        for t in self.wires(Config(2)):
            if (t.epoch == 0 and t.channel != 2) or (t.epoch == 1 and t.channel == 2):
                receiver.receive(110, t.wire)
        self.assertTrue(all(v['outcome'] == 'expired' for v in receiver.finalize().values()))

    def test_transcript_substitution_rejected(self):
        receiver = Receiver(KEY, SESSION, Config(1))
        other = self.wires(objects=(b'other', b'two', b'image'))
        for t in (self.wires()[0], other[1], self.wires()[2]):
            receiver.receive(20, t.wire)
        self.assertEqual(receiver.finalize()[0]['outcome'], 'expired')
        self.assertEqual(receiver.counts['transcript_conflict'], 1)

    def test_full_transcript_hash_checked(self):
        receiver = Receiver(KEY, SESSION, Config(1))
        for channel, payload in enumerate(OBJECTS, 1):
            receiver.receive(20, encode(KEY, SESSION, 0, channel, 0, payload, b'x' * 32))
        self.assertEqual(receiver.finalize()[0]['outcome'], 'expired')
        self.assertEqual(receiver.counts['transcript_hash_failure'], 1)

    def test_exact_deadline_is_inclusive(self):
        result = simulate(KEY, SESSION, [OBJECTS], (0, 0, 0), Config(1), delay_ms=500)
        self.assertEqual(result['outcomes'][0]['outcome'], 'complete')

    def test_late_last_object_cannot_trigger_acceptance(self):
        receiver = Receiver(KEY, SESSION, Config(1, deadline_ms=20))
        for t in self.wires():
            receiver.receive(1000 if t.channel == 3 else 0, t.wire)
        self.assertEqual(receiver.finalize()[0]['outcome'], 'expired')
        self.assertEqual(receiver.counts['late'], 1)

    def test_one_millisecond_late_expires(self):
        result = simulate(KEY, SESSION, [OBJECTS], (0, 0, 0), Config(1), delay_ms=501)
        self.assertEqual(result['outcomes'][0]['outcome'], 'expired')

    def test_duplicate_delivery_prevented(self):
        result = simulate(KEY, SESSION, [OBJECTS], (1, 1, 1), Config(1))
        self.assertEqual(len(result['outcomes']), 1)
        self.assertEqual(result['event_counts']['post_completion_duplicate'], 3)

    def test_copy_can_replace_lost_original(self):
        result = simulate(KEY, SESSION, [OBJECTS], (1, 0, 0), Config(1), natural_drop=lambda t: t.channel == 1 and t.copy == 0)
        self.assertEqual(result['outcomes'][0]['completion_ms'], 120)

    def test_copies_are_impaired_too(self):
        result = simulate(KEY, SESSION, [OBJECTS], (1, 0, 0), Config(1), natural_drop=lambda t: t.channel == 1)
        self.assertEqual(result['outcomes'][0]['outcome'], 'expired')
        self.assertEqual(result['natural_loss_objects'], 2)

    def test_spread_boundary_and_copy_refresh(self):
        for last, expected in ((300, 'complete'), (301, 'expired')):
            receiver = Receiver(KEY, SESSION, Config(1))
            for t in self.wires():
                receiver.receive(last if t.channel == 3 else 0, t.wire)
            self.assertEqual(receiver.finalize()[0]['outcome'], expected)
        receiver = Receiver(KEY, SESSION, Config(1))
        frames = self.wires()
        for t in frames:
            receiver.receive(301 if t.channel == 3 else 0, t.wire)
        for t in frames[:2]:
            receiver.receive(302, t.wire)
        self.assertEqual(receiver.finalize()[0]['outcome'], 'complete')

    def test_future_and_out_of_window_do_not_advance_state(self):
        receiver = Receiver(KEY, SESSION, Config(2, window=1))
        future = self.wires(Config(2))[3]
        receiver.receive(0, future.wire)
        receiver.receive(100, future.wire)
        self.assertEqual(receiver.counts['before_release'], 1)
        self.assertEqual(receiver.counts['out_of_window'], 1)
        self.assertFalse(receiver.buffers)
        self.assertEqual(len(receiver.finalize()), 2)

    def test_unknown_epoch_rejected(self):
        receiver = Receiver(KEY, SESSION, Config(1))
        receiver.receive(10, encode(KEY, SESSION, 99, 1, 0, b'x', b'x' * 32))
        self.assertEqual(receiver.counts['unknown_epoch'], 1)

    def test_nonmonotone_and_closed_receivers_rejected(self):
        receiver = Receiver(KEY, SESSION, Config(1))
        receiver.receive(20, self.wires()[0].wire)
        with self.assertRaises(ValueError):
            receiver.receive(19, self.wires()[1].wire)
        receiver.finalize()
        with self.assertRaises(ValueError):
            receiver.receive(30, self.wires()[1].wire)

    def test_bytes_reconcile_all_eight_policies_even_when_lost(self):
        for policy in POLICIES:
            result = simulate(KEY, SESSION, [OBJECTS] * 2, policy, Config(2), natural_drop=lambda t: True)
            self.assertEqual(result['emitted_bytes'], 2 * costs(tuple(map(len, OBJECTS)), policy)['total_bytes'])
            self.assertEqual(result['emitted_objects'], 2 * (3 + sum(policy)))

    def test_hard_defender_budget_and_exact_boundary(self):
        sizes = (10, 10, 10)
        self.assertTrue(feasible(sizes, (1, 1, 1), 1))
        self.assertFalse(feasible(sizes, (1, 1, 1), '0.999999'))
        self.assertFalse(feasible(sizes, (0, 0, 1), 0))
        self.assertTrue(feasible(sizes, (0, 0, 0), 0))

    def test_attacker_budget_fixed_across_defences(self):
        for policy in ((0, 0, 0), (1, 1, 1)):
            ledger = SuppressionBudget(100, '0.05')
            result = simulate(KEY, SESSION, [OBJECTS] * 100, policy, Config(100), attacker=ledger, target_channel=3)
            self.assertEqual(ledger.cap, 15)
            self.assertEqual(ledger.spent, 15)
            self.assertEqual(result['suppressed_objects'], 15)

    def test_attack_block_cap_no_carry_and_partial_block(self):
        ledger = SuppressionBudget(205, '0.05')
        for t in self.wires(Config(205)):
            if t.epoch >= 100:
                ledger.decide(t)
        self.assertEqual(ledger.blocks, {1: 15})
        self.assertEqual(ledger.spent, 15)
        self.assertEqual(ledger.cap, 30)

    def test_natural_loss_not_disclosed_and_does_not_refund_attack(self):
        ledger = SuppressionBudget(1, 1)
        result = simulate(KEY, SESSION, [OBJECTS], (0, 0, 0), Config(1), attacker=ledger, natural_drop=lambda t: True)
        self.assertEqual(ledger.spent, 3)
        self.assertEqual(result['wasted_suppressions'], 3)
        self.assertEqual(result['natural_loss_objects'], 3)

    def test_copies_consume_separate_attack_actions(self):
        ledger = SuppressionBudget(1, 1)
        result = simulate(KEY, SESSION, [OBJECTS], (1, 0, 0), Config(1), attacker=ledger, target_channel=1)
        self.assertEqual(ledger.spent, 2)
        self.assertEqual(result['outcomes'][0]['outcome'], 'expired')

    def test_attack_input_cannot_be_replayed_or_time_reversed(self):
        ledger = SuppressionBudget(1, 1)
        original = self.wires()[0]
        ledger.decide(original)
        with self.assertRaises(ValueError):
            ledger.decide(original)
        with self.assertRaises(ValueError):
            ledger.decide(replace(self.wires()[1], send_ms=-1))

    def test_recorded_extraction_failure_remains_failure_with_copies(self):
        result = simulate(KEY, SESSION, [OBJECTS] * 2, (1, 1, 1), Config(2))
        self.assertEqual(extraction_weighted_completion(result['outcomes'], {0: 0, 1: 1}), 1)
        with self.assertRaises(ValueError):
            extraction_weighted_completion(result['outcomes'], {0: 1})

    def test_invalid_configuration_fails_closed(self):
        for args in ({'epochs': 0}, {'epochs': 1, 'window': 0}, {'epochs': 1, 'deadline_ms': -1}):
            with self.assertRaises(ValueError):
                Config(**args)
        with self.assertRaises(ValueError):
            costs((1, 2, 3), (2, 0, 0))
        with self.assertRaises(ValueError):
            SuppressionBudget(1, -0.1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
