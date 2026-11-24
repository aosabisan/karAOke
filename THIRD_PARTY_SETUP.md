# The free tools Aosabi Karaoke works with

None of these is part of Aosabi Karaoke, and none is included in this package. You install them yourself, each
with its **Install** button on the Setup tab, from the official source named here. Each one keeps its own licence,
and each goes into its own folder under `%LOCALAPPDATA%\AosabiKaraoke\engines\`, where **Remove** deletes it again.

| Tool | What it is for | Official source | Licence (check it yourself before paid work) |
|---|---|---|---|
| uv (Astral) | Sets up the private Python environments | https://docs.astral.sh/uv/ | MIT / Apache-2.0 |
| Python, numpy, aiohttp | What the Karaoke program itself runs on | https://pypi.org | PSF, BSD, Apache-2.0 |
| audio-separator | Splits a song into music and singing | https://github.com/nomadkaraoke/python-audio-separator | MIT for the program. **Every splitting model has its own terms.** |
| rvc-python | Sings with an RVC voice model | https://github.com/daswer123/rvc-python | MIT |
| so-vits-svc-fork | Sings with a so-vits-svc voice model | https://github.com/voicepaw/so-vits-svc-fork | Apache-2.0 / MIT |
| PyTorch | Used by all three tools | https://pytorch.org | BSD-style |
| Applio (optional) | Your own RVC program, if you already use it | https://applio.org | Its own terms |

## About the splitting models

The splitter downloads the model you picked the first time it is used. The three choices on the Setup tab are
models the audio-separator project offers; people outside that project trained them, and their licences are not
always stated clearly. If you use the results for paid work, read the terms of the model you chose, or type the
file name of a model whose terms you are happy with into the splitting-model setting.

## Which graphics card setting

- **No NVIDIA card**: everything works, but a three-minute song can take many minutes to split.
- **NVIDIA (GTX / RTX 20, 30, 40)** and **NVIDIA RTX 50-series**: installs the matching PyTorch build from
  pytorch.org so the tools use the card.

Choose it before you press Install. To change it later, Remove the tool and Install it again.

## If an install stops with an error

The message under "Working on" shows the last lines the installer printed. Most often it is a dropped download:
press Install again (finished parts are kept). `ffmpeg` is needed by the splitter for some file types; if it asks
for it, install ffmpeg from https://ffmpeg.org and add the song again, or convert the song to WAV first.
