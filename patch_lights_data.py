#!/usr/bin/env python3
"""
Asterix & Obelix XXL Romastered, Steam macOS build 0.34: make the five sector
lighting streams that contain an oCX1FarZoneGo object loadable by the Mac binary,
which does not have that class.

How it works
------------
GameStream files carry a class table (per entry: u32 name length, name, u32 class
id, u32 version major, u32 version minor, u32 parent id). Objects point at classes
by table index, and the engine resolves a class by its numeric id, never by name.
oCX1FarZoneGo (id 0x14acaf29, unknown to the Mac binary) serializes exactly like
its parent oCRenderSettingsZoneGo (id 0x113a8d9d, known) plus one trailing float,
the far distance. So each FarZone object is retyped to its parent:
  (a) object-list class index   -> index of oCRenderSettingsZoneGo
  (b) object header class index -> same
  (c) delete the trailing 4-byte float right before the object's END marker
  (d) the two stream size fields at 0xab and 0xaf (= filesize - 0xb7) minus 4
The now unused oCX1FarZoneGo class-table entry can stay, unused entries are never
resolved. The sector keeps its render-settings zone, only the far-distance value
is lost.

Every edit is checked against the expected original bytes first. Each file is
backed up once as <file>.orig.

Usage:
    python3 patch_lights_data.py                  # apply, default Steam location
    python3 patch_lights_data.py "/path/to/Asterix & Obelix XXL 1"
    python3 patch_lights_data.py --restore        # put the .orig backups back

Run fix_sector_streams.py first. Without it the binary still aborts the sector
load on any other hiccup; with both, the sectors load with their full lighting.
"""
import glob
import os
import shutil
import struct
import sys

DEFAULT_GAME_DIR = os.path.expanduser(
    "~/Library/Application Support/Steam/steamapps/common/Asterix & Obelix XXL 1")
LEVELS_REL = "Contents/Resources/XXL1Resources/_Cooking/Levels"
BEGIN_MARK = bytes.fromhex("1111bbaa")  # 0xaabb1111 little-endian
END_MARK = bytes.fromhex("2222bbaa")    # 0xaabb2222 little-endian

# file: (size, list_off, old_idx, new_idx, hdr_off, float_off, float_bytes, size_old, size_new)
EDITS = {
    "02_Normandie/LVL02_SEC02_LightsRmt": (0xdb2, 0x7a9, 0x0e, 0x0b, 0x9bf, 0xa38, "0000fa43", 0x0cfb, 0x0cf7),
    "02_Normandie/LVL02_SEC09_LightsRmt": (0x4e0e, 0x74a, 0x0d, 0x04, 0x90e, 0x987, "00007a44", 0x4d57, 0x4d53),
    "04_Helvetie/LVL04_SEC09_LightsRmt": (0x80a, 0x538, 0x0c, 0x04, 0x62b, 0x6a4, "00805444", 0x0753, 0x074f),
    "05_Egypt/LVL05_SEC04_LightsRmt": (0x840, 0x535, 0x0c, 0x04, 0x62e, 0x6a7, "00007a44", 0x0789, 0x0785),
    "05_Egypt/LVL05_SEC09_LightsRmt": (0x6f97, 0x9a3, 0x0f, 0x04, 0x10e9, 0x1162, "00002f44", 0x6ee0, 0x6edc),
}


def find_levels_dir(game_dir):
    apps = sorted(glob.glob(os.path.join(game_dir, "*.app")))
    if not apps:
        sys.exit(f"No .app bundle found in {game_dir!r}.\n"
                 "Pass the game folder as an argument, e.g.\n"
                 '  python3 patch_lights_data.py "/Volumes/MyDrive/SteamLibrary/steamapps/common/Asterix & Obelix XXL 1"')
    levels = os.path.join(apps[0], LEVELS_REL)
    if not os.path.isdir(levels):
        sys.exit(f"Levels folder not found at {levels!r}.")
    return levels


def check(cond, msg):
    if not cond:
        sys.exit("ABORT, nothing written: " + msg)


def classes(d):
    """Parse every class table (BEGIN, count, entries) and return the one that lists oCX1FarZoneGo."""
    pos = 0
    while True:
        i = d.find(BEGIN_MARK, pos)
        if i < 0:
            return None
        pos = i + 4
        try:
            n = struct.unpack_from("<I", d, i + 4)[0]
            if not 1 <= n <= 0x200:
                continue
            j = i + 8
            names = []
            for _ in range(n):
                ln = struct.unpack_from("<I", d, j)[0]
                if not 2 <= ln <= 64:
                    raise ValueError
                nm = d[j + 4:j + 4 + ln].decode("ascii")
                j += 4 + ln + 16
                if not nm.startswith("o"):
                    raise ValueError
                names.append(nm)
        except (ValueError, UnicodeDecodeError, struct.error):
            continue
        if "oCX1FarZoneGo" in names:
            return names


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    game_dir = args[0] if args else DEFAULT_GAME_DIR
    levels = find_levels_dir(game_dir)

    def path(k):
        return os.path.join(levels, k + ".level.ot.GameStream.gen")

    if "--restore" in flags:
        n = 0
        for k in EDITS:
            if os.path.exists(path(k) + ".orig"):
                shutil.copy2(path(k) + ".orig", path(k))
                n += 1
        print(f"Restored {n} of {len(EDITS)} lighting files from their .orig backups.")
        return

    plans = []
    for k, (size, loff, oi, ni, hoff, foff, fhex, s_old, s_new) in EDITS.items():
        f = path(k)
        check(os.path.isfile(f), f"{k}: file not found at {f!r}")
        d = open(f, "rb").read()
        if len(d) == size - 4 and struct.unpack_from("<I", d, 0xab)[0] == s_new:
            print("already patched:", k)
            continue
        check(len(d) == size, f"{k}: size {len(d):#x} != {size:#x}")
        check(struct.unpack_from("<I", d, loff)[0] == oi, f"{k}: object-list index @{loff:#x}")
        check(struct.unpack_from("<I", d, hoff)[0] == oi, f"{k}: object header index @{hoff:#x}")
        check(d[hoff - 4:hoff] == BEGIN_MARK, f"{k}: no BEGIN before object header")
        check(d[foff:foff + 4] == bytes.fromhex(fhex), f"{k}: far-distance float @{foff:#x}")
        check(d[foff + 4:foff + 8] == END_MARK, f"{k}: END marker after float")
        check(struct.unpack_from("<I", d, 0xab)[0] == s_old and struct.unpack_from("<I", d, 0xaf)[0] == s_old,
              f"{k}: size fields @0xab/0xaf")
        check(s_old == size - 0xb7, f"{k}: size field != filesize-0xb7")
        # the old index must really be the FarZone class and the new one its parent
        names = classes(d)
        check(names is not None, f"{k}: no class table with oCX1FarZoneGo")
        check(names[oi] == "oCX1FarZoneGo", f"{k}: class[{oi}] is {names[oi]!r}")
        check(names[ni] == "oCRenderSettingsZoneGo", f"{k}: class[{ni}] is {names[ni]!r}")
        plans.append((k, f, bytearray(d), loff, hoff, foff, ni, s_new))

    if not plans:
        print("Nothing to do.")
        return
    for k, f, d, loff, hoff, foff, ni, s_new in plans:
        if not os.path.exists(f + ".orig"):
            shutil.copy2(f, f + ".orig")
        struct.pack_into("<I", d, loff, ni)
        struct.pack_into("<I", d, hoff, ni)
        struct.pack_into("<I", d, 0xab, s_new)
        struct.pack_into("<I", d, 0xaf, s_new)
        del d[foff:foff + 4]          # last, this shifts everything after it
        open(f, "wb").write(d)
        print(f"patched {k}: {len(d) + 4:#x} -> {len(d):#x} bytes")
    print("Done. Backups sit next to each file as .orig")


if __name__ == "__main__":
    main()
