"""Runs inside the rvc-python environment (which you install from the Setup page): sings one vocal track with an
RVC voice model. Part of Aosabi Karaoke; rvc-python itself is not included."""
import argparse

ap = argparse.ArgumentParser()
ap.add_argument("--input", required=True)
ap.add_argument("--output", required=True)
ap.add_argument("--model", required=True)
ap.add_argument("--index", default="")
ap.add_argument("--pitch", type=int, default=0)
a = ap.parse_args()

import torch  # noqa: E402  (third-party, installed by the user)
from rvc_python.infer import RVCInference  # noqa: E402

device = "cuda:0" if torch.cuda.is_available() else "cpu:0"
print(f"Loading the voice model on {'your NVIDIA card' if device.startswith('cuda') else 'the processor (slow)'}...", flush=True)
rvc = RVCInference(device=device)
rvc.load_model(a.model, index_path=a.index)
rvc.set_params(f0up_key=a.pitch, f0method="rmvpe", index_rate=0.5 if a.index else 0.0, protect=0.33)
print("Singing the vocal track with the voice model...", flush=True)
rvc.infer_file(a.input, a.output)
print("Done.", flush=True)
