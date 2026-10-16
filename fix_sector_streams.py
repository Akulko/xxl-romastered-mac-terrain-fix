#!/usr/bin/env python3
"""
Asterix & Obelix XXL Romastered, Steam macOS build 0.34: bring back the invisible
ground in the slide and pre-fight sections of Normandy, Helvetia and Egypt.

What is wrong
-------------
The Mac binary is older than the game data it ships with. Five sector lighting
streams (LVL02_SEC02, LVL02_SEC09, LVL04_SEC09, LVL05_SEC04, LVL05_SEC09,
*_LightsRmt.level.ot.GameStream.gen) contain one object of class oCX1FarZoneGo.
This binary has no such class. Deserializing the stream fails, the stream registry
treats a failed linked stream as fatal (the `cmpb $0,(registry)` checks in the
loader), and the whole LVLxx_SECyy sector load fails. Nothing in that sector gets
spawned: no terrain, grass, rocks, atlas materials or lighting. Collision comes
from separate data, so you walk on nothing.

What this script does
---------------------
It NOPs the four `je <fail>` branches that follow the `cmpb $0,(registry)` checks
in LoadStream (0x100fa8132) and RegisterStream (0x100fa7afe), which is what the
engine's own tolerant mode does. A linked stream that fails is dropped instead of
killing the sector. Then it re-signs the app with an ad-hoc signature.

Every byte is checked against the expected original before anything is written,
and the binary is backed up once as <binary>.pre-sectorfix.bak.

Usage:
    python3 fix_sector_streams.py                  # apply, default Steam location
    python3 fix_sector_streams.py "/path/to/Asterix & Obelix XXL 1"
    python3 fix_sector_streams.py --restore        # put the backup back

Prerequisite: the community crash patch from
https://github.com/breckenreed/asterix-obelix-xxl-romastered-macos-patch
(Step 1 and Step 2 of its README). Steam's "Verify integrity of game files"
reverts everything, including this.
"""
import glob
import os
import shutil
import subprocess
import sys

DEFAULT_GAME_DIR = os.path.expanduser(
    "~/Library/Application Support/Steam/steamapps/common/Asterix & Obelix XXL 1")
BINARY_NAME = "Asterix & Obelix XXL _ Romastered"
BACKUP_SUFFIX = ".pre-sectorfix.bak"
BASE = 0x100000000

NOP6 = bytes.fromhex("660f1f440000")  # 6-byte nop
NOP2 = bytes.fromhex("6690")          # 2-byte nop
PATCHES = {  # vmaddr: (expected bytes, replacement)
    0x100fa8421: (bytes.fromhex("0f84e7000000"), NOP6),  # LoadStream: links-A failed -> fail
    0x100fa8446: (bytes.fromhex("7475"),         NOP2),  # LoadStream: links-B failed -> fail
    0x100fa7bcf: (bytes.fromhex("0f84af000000"), NOP6),  # RegisterStream: links-A failed -> fail
    0x100fa7bf4: (bytes.fromhex("0f84a6000000"), NOP6),  # RegisterStream: links-B failed -> fail
}
# bytes that must sit right before each patch (the cmpb $0,(%reg)), so we never patch blind
CONTEXT = {
    0x100fa8421: bytes.fromhex("41803c2400"),   # cmpb $0,(%r12)
    0x100fa8446: bytes.fromhex("41803c2400"),
    0x100fa7bcf: bytes.fromhex("41803f00"),     # cmpb $0,(%r15)
    0x100fa7bf4: bytes.fromhex("41803f00"),
}


def find_app(game_dir):
    apps = sorted(glob.glob(os.path.join(game_dir, "*.app")))
    if not apps:
        sys.exit(f"No .app bundle found in {game_dir!r}.\n"
                 "Pass the game folder as an argument, e.g.\n"
                 '  python3 fix_sector_streams.py "/Volumes/MyDrive/SteamLibrary/steamapps/common/Asterix & Obelix XXL 1"')
    return apps[0]


def find_binary(app):
    macos = os.path.join(app, "Contents", "MacOS")
    exact = os.path.join(macos, BINARY_NAME)
    if os.path.isfile(exact):
        return exact
    candidates = [f for f in sorted(os.listdir(macos))
                  if os.path.isfile(os.path.join(macos, f))
                  and not f.endswith(".dylib") and ".bak" not in f]
    if not candidates:
        sys.exit(f"No game binary found in {macos!r}.")
    return os.path.join(macos, candidates[0])


def resign(app):
    r = subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app])
    if r.returncode != 0:
        sys.exit(f"The binary was written but codesign failed (exit {r.returncode}).\n"
                 "The game will not start until the app is re-signed. Run this by hand:\n"
                 f'  codesign --force --deep --sign - "{app}"')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    game_dir = args[0] if args else DEFAULT_GAME_DIR
    app = find_app(game_dir)
    binary = find_binary(app)
    backup = binary + BACKUP_SUFFIX

    if "--restore" in flags:
        if not os.path.exists(backup):
            sys.exit(f"No backup at {backup!r}; nothing restored.")
        shutil.copy2(backup, binary)
        resign(app)
        print("Restored the binary from before this fix. Re-signed the app.")
        return

    data = bytearray(open(binary, "rb").read())
    if all(data[a - BASE:a - BASE + len(new)] == new for a, (_, new) in PATCHES.items()):
        print("Already applied, nothing to do.")
        return
    for a, (old, new) in PATCHES.items():
        off = a - BASE
        ctx = CONTEXT[a]
        if off < len(ctx) or off + len(old) > len(data) \
                or data[off - len(ctx):off] != ctx or data[off:off + len(old)] != old:
            sys.exit(f"Unexpected bytes at {a:#x}. Is this the Steam Mac build 0.34 with the\n"
                     "community crash patch applied? Nothing was changed.")
    if not os.path.exists(backup):
        shutil.copy2(binary, backup)
        print("Backed up binary to", backup)
    for a, (old, new) in PATCHES.items():
        off = a - BASE
        data[off:off + len(new)] = new
    with open(binary, "wb") as f:
        f.write(data)
    resign(app)
    print("Patched: a failed linked stream no longer aborts the sector load. Re-signed the app.")
    print("Now run patch_lights_data.py to get the sector lighting back too.")


if __name__ == "__main__":
    main()
