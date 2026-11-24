"""Runs inside the audio-separator environment (which you install from the Setup page): splits one song into
vocals.wav and instrumental.wav. Part of Aosabi Karaoke; audio-separator itself is not included."""
import argparse
import os
import shutil
import sys

ap = argparse.ArgumentParser()
ap.add_argument("--input", required=True)
ap.add_argument("--outdir", required=True)
ap.add_argument("--model", required=True)
ap.add_argument("--models-dir", required=True)
a = ap.parse_args()

from audio_separator.separator import Separator  # noqa: E402  (third-party, installed by the user)

os.makedirs(a.outdir, exist_ok=True)
os.makedirs(a.models_dir, exist_ok=True)
print(f"Loading the splitting model {a.model} (downloaded the first time)...", flush=True)
sep = Separator(output_dir=a.outdir, output_format="WAV", model_file_dir=a.models_dir)
sep.load_model(model_filename=a.model)
print("Splitting the song. This is the slow part...", flush=True)
files = [f if os.path.isabs(f) else os.path.join(a.outdir, f) for f in sep.separate(a.input)]

vocals = next((f for f in files if "vocal" in os.path.basename(f).lower() and "no_vocal" not in os.path.basename(f).lower()), None)
music = next((f for f in files if f != vocals), None)
if not vocals or not music:
    sys.exit(f"The model wrote these files, and a vocal and a music track could not be told apart: {[os.path.basename(f) for f in files]}")
shutil.move(vocals, os.path.join(a.outdir, "vocals.wav"))
shutil.move(music, os.path.join(a.outdir, "instrumental.wav"))
print("Done.", flush=True)
