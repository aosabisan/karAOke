import json
import unittest

import numpy as np

from karaoke import mouth, wavio
from tests import synth


def mean(track, name, t0, t1):
    a = np.array(track["ch"][name][int(t0 * track["fps"]): int(t1 * track["fps"])], float) / 255.0
    return float(a.mean())


class MouthTrack(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sr = 44100
        # 0-1 silence, 1-2 "aa", 2-2.5 silence, 2.5-3.5 "ee", 3.5-4 silence, 4-5 "oo", 5-5.5 silence, 5.5-6 "sss", 6-7 silence
        parts = [synth.silence(1), synth.vowel("a", 1), synth.silence(.5), synth.vowel("i", 1), synth.silence(.5),
                 synth.vowel("u", 1), synth.silence(.5), synth.hiss(.5), synth.silence(1)]
        cls.x = np.concatenate(parts)
        cls.tr = mouth.analyse(cls.x, sr)

    def test_shape_of_result(self):
        tr = self.tr
        self.assertEqual(tr["fps"], 60)
        self.assertAlmostEqual(tr["n"] / tr["fps"], 7.0, delta=0.05)
        for name in mouth.CHANNELS:
            self.assertEqual(len(tr["ch"][name]), tr["n"])
        json.dumps(tr)  # plain ints only

    def test_silence_keeps_the_mouth_shut(self):
        for t0, t1 in ((0.1, 0.9), (2.25, 2.45), (6.2, 6.9)):
            self.assertLess(mean(self.tr, "jawOpen", t0, t1), 0.03)

    def test_aa_opens_the_jaw_widest(self):
        aa, ee, oo = (mean(self.tr, "jawOpen", a, b) for a, b in ((1.2, 1.9), (2.7, 3.4), (4.2, 4.9)))
        self.assertGreater(aa, 0.6)
        self.assertGreater(aa, ee + 0.15)
        self.assertGreater(aa, oo + 0.15)

    def test_ee_stretches_and_oo_rounds(self):
        self.assertGreater(mean(self.tr, "mouthStretch", 2.7, 3.4), 0.35)
        self.assertLess(mean(self.tr, "mouthStretch", 4.2, 4.9), 0.1)
        self.assertGreater(mean(self.tr, "mouthPucker", 4.2, 4.9), 0.35)
        self.assertLess(mean(self.tr, "mouthPucker", 2.7, 3.4), 0.1)

    def test_s_sound_keeps_teeth_close(self):
        self.assertLess(mean(self.tr, "jawOpen", 5.6, 5.95), 0.25)
        self.assertGreater(mean(self.tr, "level", 5.6, 5.95), 0.2)

    def test_quiet_and_loud_recordings_give_the_same_mouth(self):
        quiet = mouth.analyse(self.x * 0.1, 44100)
        self.assertAlmostEqual(mean(quiet, "jawOpen", 1.2, 1.9), mean(self.tr, "jawOpen", 1.2, 1.9), delta=0.08)

    def test_sample_between_frames_and_outside(self):
        tr = self.tr
        self.assertEqual(mouth.sample(tr, -1.0)["jawOpen"], 0.0)
        self.assertEqual(mouth.sample(tr, 99.0)["jawOpen"], 0.0)
        v = mouth.sample(tr, 1.5)
        self.assertGreater(v["jawOpen"], 0.6)
        self.assertTrue(all(0.0 <= x <= 1.0 for x in v.values()))

    def test_bass_left_over_from_the_music_does_not_open_the_mouth(self):
        t = np.arange(44100 * 2) / 44100
        kick = (0.25 * np.sin(2 * np.pi * 60 * t)).astype(np.float32)          # what a splitter may leave in the vocal track
        tr = mouth.analyse(np.concatenate([kick, synth.vowel("a", 1) + kick[:44100], kick]), 44100)
        self.assertLess(mean(tr, "jawOpen", 0.3, 1.7), 0.03)
        self.assertGreater(mean(tr, "jawOpen", 2.2, 2.9), 0.6)
        self.assertLess(mean(tr, "jawOpen", 3.4, 4.8), 0.03)

    def test_empty_and_stereo_input(self):
        self.assertEqual(mouth.analyse(np.zeros(0, np.float32), 44100)["n"], 0)
        st = mouth.analyse(np.stack([self.x, self.x], 1), 44100)
        self.assertAlmostEqual(mean(st, "jawOpen", 1.2, 1.9), mean(self.tr, "jawOpen", 1.2, 1.9), delta=0.02)


class Wav(unittest.TestCase):
    def test_round_trip_and_formats(self):
        import os, struct, tempfile
        x = (np.sin(np.arange(4410) / 10) * 0.5).astype(np.float32)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.wav")
            wavio.write_wav(p, np.stack([x, -x], 1), 44100)
            y, sr = wavio.read_wav(p)
            self.assertEqual((sr, y.shape), (44100, (4410, 2)))
            self.assertLess(np.abs(y[:, 0] - x).max(), 1e-3)
            raw = x.astype("<f4").tobytes()  # a 32-bit float file, as some voice tools write
            head = b"RIFF" + struct.pack("<I", 36 + len(raw)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 3, 1, 22050, 88200, 4, 32)
            open(p, "wb").write(head + b"data" + struct.pack("<I", len(raw)) + raw)
            y, sr = wavio.read_wav(p)
            self.assertEqual(sr, 22050)
            self.assertLess(np.abs(y[:, 0] - x).max(), 1e-6)
            open(p, "wb").write(b"not a wav")
            with self.assertRaises(wavio.WavError):
                wavio.read_wav(p)


if __name__ == "__main__":
    unittest.main()
