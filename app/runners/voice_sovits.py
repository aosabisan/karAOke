"""Runs inside the so-vits-svc-fork environment (which you install from the Setup page): sings one vocal track with
a so-vits-svc 4.x voice model. Part of Aosabi Karaoke; so-vits-svc-fork itself is not included."""
import argparse
import subprocess
import sys

ap = argparse.ArgumentParser()
ap.add_argument("--input", required=True)
ap.add_argument("--output", required=True)
ap.add_argument("--model", required=True)
ap.add_argument("--config", required=True)
ap.add_argument("--pitch", type=int, default=0)
a = ap.parse_args()

print("Singing the vocal track with the voice model...", flush=True)
# -na = keep the melody as sung (the automatic pitch guess is for speech and would flatten a song)
cmd = [sys.executable, "-m", "so_vits_svc_fork", "infer", a.input, "-o", a.output, "-m", a.model, "-c", a.config,
       "-t", str(a.pitch), "-na"]
sys.exit(subprocess.call(cmd))
