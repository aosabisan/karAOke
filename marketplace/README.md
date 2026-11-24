# The Marketplace content: two rooms and one asset pack

This folder is laid out the way VTube Pro's Marketplace tool expects, so it can be used directly as its source:

| Listing | Kind | Where |
|---|---|---|
| Karaoke Room | room (Environment) | `assets/scenes/karaoke_room/` |
| Karaoke Stage | room (Environment) | `assets/scenes/karaoke_stage/` |
| Karaoke Props | asset pack, 9 objects to place | `props/karaoke_props/` |

Everything in them is a **grey-box placeholder**. The floor plans (`preview.png` in each room) show where the
standing and sitting places, cameras, screen and door are.

## Putting the real art in

- **Rooms:** replace `scene.glb` and keep the node names (`SPOT_01`..., `CAM_WIDE`, `CAM_REACT`, `SCREEN`, `DOOR`,
  `DOOR_OUTSIDE`, `PATH_01`...). Replace `preview.png` and `thumb.png` with real pictures.
- **Asset pack:** one `.glb` per object, its origin at the bottom centre and its front towards +Z, plus a thumbnail.
  Update the object's line in `props.json` (triangles, size in metres). At most 20,000 triangles and 8 meshes each.
- Or change the sizes in `build_placeholders.py` and run it again (needs numpy; Pillow for the pictures).

## Building the packs

    build_packs.cmd "D:\path\to\VTube Pro folder"

It runs VTube Pro's own tool three times with the card texts from `cards.json` and writes the packs to
`packs-out\`. Nothing is uploaded. Publishing is a separate, deliberate step you run yourself in the VTube Pro
folder (`npm run dlc:publish` shows what would go out; it only uploads with `-- --confirm`).

Three things to know:

1. **The signing key.** Helpers only install packs signed with the Marketplace's trusted key. The tool reads it
   from `VTP_DLC_SIGNING_KEY` or `%USERPROFILE%\.vtubepro\dlc-signing.pem`. Without that key the packs still
   build, but nobody's helper will accept them.
2. **Price.** The tool has no price setting yet and refuses anything above 0, so the listings are free. When
   paid listings open, the same packs are listed again with a price: nothing inside them changes.
3. **Licence.** The cards are built without a licence, and the Marketplace then shows its default
   "VTube Pro licence". To show your own, add `--license <your id> --license-summary "..." --license-url https://...`
   to the three commands in `build_packs.cmd`.

## Why the packs are not called "aosabi_..."

VTube Pro's Marketplace tool refuses any pack whose id or files contain certain personal names, and "aosabi" is
on that list (it treats such packs as personal builds). So the ids are `karaoke_room`, `karaoke_stage` and
`karaoke_props`, and no file inside the packs carries the name. The **"by aosabi" credit on the card is accepted**
and is set in `build_packs.cmd`. Using the name in ids or files would need that list changed in VTube Pro's tool.

## What was checked

All three were built into real `.vtpdlc` packs with VTube Pro's own tool (with a throwaway test key, in a private
workspace): the safety check passed, the asset pack counted 9 objects, and the listings came out as free, by
aosabi. Both rooms pass VTube Pro's room checker ("Ready to use"), and all 11 model files pass the glTF validator
with 0 errors. None of it has been looked at inside the app yet.
