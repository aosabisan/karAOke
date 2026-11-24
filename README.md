# Aosabi Karaoke

A karaoke add-on for VTube Pro, by aosabi. It runs as its own small program next to VTube Pro and plugs into it
through VTube Pro's plugin door (the same one VTube Studio plugins use), so VTube Pro itself is not changed.

What it does:

- You add a song file. It is split **on your computer** into the music and the singing. Nothing is uploaded.
- The music plays. The singing can be silent, the original singer, or **sung by a voice model** (RVC or
  so-vits-svc), for example a model of your own voice.
- Your avatar's **mouth follows the singing**, with a switch to turn that off. Your head and body keep following
  your camera.
- Your avatar can do VTube Pro's looping **dance** while the song plays.
- Marketplace content comes with it: two placeholder rooms (a karaoke room and a stage) and an asset pack of
  their furniture (see `marketplace/`).

## Start it

Double-click **Start Karaoke.cmd**. The first time it sets up a small private Python for the program (it asks
before downloading anything). Then the Karaoke page opens in your browser at `http://127.0.0.1:5290/`.
Keep the black window open while you sing; closing it stops the program.

## Connect it to VTube Pro (once)

Open the **Setup** tab on the Karaoke page and follow step 1:

1. In VTube Pro, open the **Track** tab, find **External tracking** and switch on **VTube Studio API (plugins)**.
2. Press **Connect** on the Karaoke page, then press **Allow** next to "Aosabi Karaoke" in that same list.
3. In the same place, set **Drive the avatar from** to **VTube Studio API plugins**.

The chip at the top of the Karaoke page turns green ("VTube Pro: connected"). While no song is playing, your
camera and microphone drive the avatar exactly as before.

## Install the tools that do the heavy work (once)

Splitting songs and changing voices is done by free tools made by other people. They are **not included**: on the
Setup tab you install each one with its own button, from its official source. See `THIRD_PARTY_SETUP.md`.
Do this when you are not live; each tool is a few gigabytes.

No tools yet? You can still add a song if you already have its music and its vocals as two WAV files
("I already have the music and the vocals" on the Sing tab).

## Sing

1. **Add a song**: choose the file and how the vocals should play (left out, the original singer, or a voice
   model). The song appears under "Your songs" when it is ready. Splitting takes a while, most of all without
   an NVIDIA graphics card.
2. Press **Load** next to a song, then **Play**.
3. While it plays you can switch the vocals, switch **Mouth follows the singing** and **Dance** on or off, set the
   two volumes, and nudge **Mouth timing** until the mouth matches what you hear.

Your stream hears the song the same way it hears any other sound from your computer (OBS "Desktop Audio").
Wear headphones if your microphone would otherwise pick the music up.

## Voice models

Put your models in the voices folder shown on the Setup tab and press Refresh, or type the folder you already
keep them in into the box under it (the models are read from there, nothing is copied or changed).

- **RVC**: the `.pth` file, with its `.index` file beside it if you have one.
- **so-vits-svc 4.x**: a folder holding `G_....pth` and `config.json`.
- **Anything else**: Setup has a box for the command line of any other voice tool.

"Pitch" moves the melody up or down in half steps so a song suits the voice (12 = one octave).
Only use a voice you have the right to use: your own, or one you have the person's permission for.

## Good to know

- **Blinks and brows.** While the mouth follows a song, VTube Pro takes the whole face from the plugin, so the
  plugin blinks for you and your brows rest. Head, body and hands stay on your camera. Switch "Mouth follows the
  singing" off and your own face is back within half a second.
- **The dance** is VTube Pro's built-in "dance" loop. In a room VTube Pro plays only its upper body.
- **Music rights.** Playing commercial songs on a stream can get the stream muted or taken down, also with the
  vocals replaced. That is between you and the platform.
- **Where your things are:** `%LOCALAPPDATA%\AosabiKaraoke` (songs, settings, the installed tools). Deleting that
  folder removes everything the program ever wrote.
- **Not on the VTube Pro Marketplace as a program yet:** the Marketplace lists rooms, characters and asset packs.
  The two rooms and the asset pack are built for it (see `marketplace/`); the program is this folder.

## What has and has not been tested

Tested, always without sound, and only against a private copy of VTube Pro's helper (never a live one):

- the plugin login (the Allow step) and the mouth reaching VTube Pro's bus about 60 times a second;
- that VTube Pro's own studio code turns those values into an open, wide or round mouth while your microphone is silent;
- the page itself in a muted browser: add a song, Load, Play, Pause, the mouth switch;
- the dance start and stop commands;
- a real install of all three tools through the Install buttons (on Linux), and a real split of a test song;
- both rooms against VTube Pro's own room checker ("Ready to use"), and the two rooms and the asset pack built
  into real Marketplace packs with VTube Pro's own tool (test key);
- an RVC v2 voice model with its index file is recognised and passed to the RVC tool correctly.

Not tested yet:

- how the mouth looks on a real avatar with a real song (it has only been measured, not watched);
- `Start Karaoke.cmd` and the tool installs on Windows;
- the two voice changers with a real voice model (their install and their interfaces were checked, a real
  conversion was not);
- the rooms and props inside the app (framing and positions are a first guess).

The checks live in `app/tests/`.
