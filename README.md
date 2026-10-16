# Invisible terrain fix for Asterix & Obelix XXL Romastered on macOS

It took me a while to figure out, but it is not a rendering problem at all. The Mac binary does not know one object type that sits in the level data, and because of that it never loads those sectors. This repo has two Python scripts that fix it. They only change your own local copy of the game. There are no game files in here.

I tested this on build 0.34, on an M2 Mac, launching from Steam like normal.

## Before you start

You need the community crash patch by breckenreed first: https://github.com/breckenreed/asterix-obelix-xxl-romastered-macos-patch

Do Step 1 (the launch fix) and Step 2 (`apply_patch.py`) from its README. Without it the game crashes when you enter Normandy anyway, and my scripts expect that patched binary.

Python 3 comes with macOS, you do not need to install anything.

## Apply

Clone or download this repo, then in Terminal:

```bash
cd /path/to/xxl-romastered-mac-terrain-fix
python3 fix_sector_streams.py
python3 patch_lights_data.py
```

The first script changes four short byte ranges in the game binary and re-signs the app. The second one edits five lighting files in the level data. Both compare every byte they are about to change against what they expect and stop without writing if anything is off. Both back up before writing: the binary as `<binary>.pre-sectorfix.bak`, each lighting file as `<file>.orig`.

If your Steam library lives somewhere else, pass the game folder to both scripts:

```bash
python3 fix_sector_streams.py "/Volumes/MyDrive/SteamLibrary/steamapps/common/Asterix & Obelix XXL 1"
```

Then start the game from Steam. Walk into the Normandy slide and the ground is there.

The first script alone already brings the terrain back. The second one also restores the remaster lighting and render settings of those sectors, see below for why.

## Undo

```bash
python3 fix_sector_streams.py --restore
python3 patch_lights_data.py --restore
```

## Steam will undo this

"Verify integrity of game files" in Steam puts the original files back. That removes the community patch and both fixes from here. If that happens, redo Step 1 and Step 2 of the community patch, then run the two scripts again.

## What was actually wrong

The Mac build of the game is from October 2020. Windows got patches 1.0.33 in November 2020 and 1.0.34 in September 2021. The Mac depot never got a new binary, but the game data on Mac is the newer data. So the Mac binary is older than the data it has to load.

Five sector lighting streams contain one object of class `oCX1FarZoneGo` (class id 0x14acaf29):

```
Levels/02_Normandie/LVL02_SEC02_LightsRmt.level.ot.GameStream.gen
Levels/02_Normandie/LVL02_SEC09_LightsRmt.level.ot.GameStream.gen
Levels/04_Helvetie/LVL04_SEC09_LightsRmt.level.ot.GameStream.gen
Levels/05_Egypt/LVL05_SEC04_LightsRmt.level.ot.GameStream.gen
Levels/05_Egypt/LVL05_SEC09_LightsRmt.level.ot.GameStream.gen
```

That class does not exist in the Mac binary. The id appears nowhere in it. When the engine deserializes one of these streams it hits the unknown class and fails. The stream registry treats a failed linked stream as fatal, so the whole `LVLxx_SECyy` sector load fails and the sector spawns nothing: no terrain, no grass, no rocks, no atlas materials, no lighting. The collision comes from the old engine's KWN data, which loads on its own. That is why you can still walk on the invisible ground.

The same failure made the `LVLxx_All` preload return null. That null pointer is the crash the community patch catches with its null check, so the crash and the invisible terrain come from the same failed load.

Gaul, Greece and Rome have no FarZone objects in their lighting streams, so they load.

### fix_sector_streams.py

In the stream loader there are four `je fail` branches right after a `cmpb $0,(registry)` check, at 0x100fa8421, 0x100fa8446, 0x100fa7bcf and 0x100fa7bf4. The script replaces them with NOPs and re-signs the app with an ad-hoc signature. When a linked stream fails to deserialize the loader now drops it and the rest of the sector loads. With only this, the terrain is back but the five sectors lose their remaster lighting object.

### patch_lights_data.py

A GameStream file has a class table. Each entry is a u32 name length, the name, a u32 class id, u32 version major, u32 version minor and a u32 parent id. Objects point at classes by table index, and the engine resolves a class by its numeric id. It never looks at the name.

`oCX1FarZoneGo` serializes the same way as its parent `oCRenderSettingsZoneGo` (id 0x113a8d9d) plus one trailing float, the far distance. So the script retypes each FarZone object to its parent in two places (the object list and the object header), deletes the trailing float and reduces the two stream size fields at 0xab and 0xaf (they equal filesize minus 0xb7) by 4. The Mac binary then loads the stream like any other. The only thing lost is that far-distance value of one zone per sector.

## How it was found

I wrote a small dylib and injected it with `DYLD_INSERT_LIBRARIES` to log GL calls, file opens and the sector streaming state from inside the game. That showed the terrain draw calls never happened, so culling was out. Breakpoints in lldb on the stream loader showed `LVL02_SEC02_LightsRmt` failing at deserialize. Then I pulled every class name out of the stream files and compared them with the RTTI names in the binary. `oCX1FarZoneGo` was the only one missing. Static disassembly of the loader confirmed that classes resolve by id and showed the object layout, which gave the second script. I then checked both fixes in game from a normal Steam launch.

## Credits

breckenreed's https://github.com/breckenreed/asterix-obelix-xxl-romastered-macos-patch fixes the launch config and the combat-world crash. Without it there is no game to test on, and its notes saved me the dead ends.
