@echo off
setlocal EnableExtensions
rem Builds the three Marketplace packs (Karaoke Room, Karaoke Stage, Karaoke Props) with VTube Pro's own tool.
rem Usage:  build_packs.cmd "D:\path\to\VTube Pro folder"
rem It signs with your Marketplace key (VTP_DLC_SIGNING_KEY, or %USERPROFILE%\.vtubepro\dlc-signing.pem).
rem Nothing is uploaded or published: the packs are written to the "packs-out" folder next to this file.

if "%~1"=="" (
  echo Usage: build_packs.cmd "path to the VTube Pro folder"
  exit /b 2
)
set "SRC=%~dp0."
set "OUT=%~dp0packs-out"
pushd "%~1" || exit /b 1

call npx tsx tools/dlc/add.ts --kind room --id karaoke_room --title "Karaoke Room" --tagline "A cosy karaoke lounge" --description "Step onto the little riser, face the couches and sing: a small karaoke lounge with a big screen behind you." --inside "Singer and duet spots on the riser|Four couch seats for friends|A big screen for React mode|Three cameras, including a singer close-up" --author aosabi --picture "%SRC%\assets\scenes\karaoke_room\preview.png" --src-root "%SRC%" --out "%OUT%" --yes || goto :failed

call npx tsx tools/dlc/add.ts --kind room --id karaoke_stage --title "Karaoke Stage" --tagline "A concert stage of your own" --description "A raised stage with a truss, monitors and a huge screen wall, seen from the crowd." --inside "Four spots on the stage|Two spots down in the crowd|A screen wall for React mode|Four cameras, including a crowd view" --author aosabi --picture "%SRC%\assets\scenes\karaoke_stage\preview.png" --src-root "%SRC%" --out "%OUT%" --yes || goto :failed

call npx tsx tools/dlc/add.ts --kind props --id karaoke_props --title "Karaoke Props" --tagline "Furniture and stage pieces" --description "The couch, table, riser, stage pieces, truss, monitor, microphone stand and neon strip from the karaoke rooms, to place in any room." --inside "Couch and coffee table|Singer riser, stage deck and steps|Lighting truss and floor monitor|Microphone stand|Neon light strip" --author aosabi --picture "%SRC%\props\karaoke_props\thumbs\couch.png" --src-root "%SRC%" --out "%OUT%" --yes || goto :failed

popd
echo.
echo Done. The three packs are in "%OUT%". Nothing was uploaded.
exit /b 0

:failed
popd
echo.
echo The build stopped. The lines above say why.
exit /b 1
