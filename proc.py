import cv2
import numpy as np
import matplotlib.pyplot as plt
import sys
import os
from pathlib import Path

INPUT_FILE_PATH = Path(sys.argv[1])
INPUT_BASENAME = os.path.basename(INPUT_FILE_PATH).split(".")[0]
OUTPUT_DIR = Path(__file__).parent / "local"

VIDEO_FPS = 0

def iter_video_frames():
    global VIDEO_FPS
    cap = cv2.VideoCapture(INPUT_FILE_PATH)

    if not cap.isOpened():
        raise RuntimeError(f"Could not open {INPUT_FILE_PATH!r}")

    VIDEO_FPS = cap.get(cv2.CAP_PROP_FPS)

    try:
        while True:
            success, frame = cap.read()

            if not success:
                return

            yield frame
    finally:
        cap.release()

black_counts = {}
white_counts = {}

blocks_per_frame = []
rle_frames = []

MAX_RUN_LEN = 8
MIN_RUN_LEN = 2
MAX_PIXEL_RUN_LEN = MAX_RUN_LEN + MIN_RUN_LEN - 1

def coalesce(runs):
    res = []

    for v, l in runs:
        v = bool(v)
        l = int(l)

        if res and res[-1][0] == v:
            res[-1] = (res[-1][0], res[-1][1] + l)
        else:
            res.append((v, l))

    return res


def clean_short_runs(runs):
    runs = coalesce(runs)

    while True:
        idx = next((index for index, (_, length) in enumerate(runs) if length < MIN_RUN_LEN), None)

        if idx is None:
            return runs

        if len(runs) == 1:
            raise ValueError("whaaat?")

        if idx == 0:
            _, short_length = runs[0]
            value, length = runs[1]
            runs[1] = (value, length + short_length)
            del runs[0]
        else:
            value, length = runs[idx - 1]
            _, short_length = runs[idx]
            runs[idx - 1] = (value, length + short_length)
            del runs[idx]

        runs = coalesce(runs)

def split_run(value, length):
    length = int(length)
    q, r = divmod(length, MAX_PIXEL_RUN_LEN)

    if r == 0:
        lens = [MAX_PIXEL_RUN_LEN] * q
    elif r == 1:
        if q == 0:
            raise ValueError("run is shorter than minimum")

        lens = ([MAX_PIXEL_RUN_LEN] * (q - 1) + [MAX_PIXEL_RUN_LEN - 1, MIN_RUN_LEN])
    else:
        lens = [MAX_PIXEL_RUN_LEN] * q + [r]

    return [(bool(value), chunk_length) for chunk_length in lens]

for frame_number, frame in enumerate(iter_video_frames()):
    gray_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    flat_frame = np.array([x > 200 for x in gray_frame.flatten()], dtype=bool)
    starts = np.r_[0, 1 + np.flatnonzero(flat_frame[1:] != flat_frame[:-1])]
    lengths = np.diff(np.r_[starts, flat_frame.size])
    values = flat_frame[starts]
    frame_z2 = coalesce(zip(values, lengths))

    frame_z3 = []
    for value, length in clean_short_runs(frame_z2):
        frame_z3.extend(split_run(value, length))

    blocks_per_frame.append(len(frame_z3))

    nibbles = []
    for value, length in frame_z3:
        nibble = (8 if value else 0) | (int(length) - MIN_RUN_LEN)
        nibbles.append(nibble)

        counts = white_counts if value else black_counts
        counts[length] = counts.get(length, 0) + 1

    if len(nibbles) % 2:
        nibbles.append(nibbles[-1])

    frame_bytes = []
    for index in range(0, len(nibbles) - 1, 2):
        frame_bytes.append((nibbles[index] << 4) | nibbles[index + 1])

    rle_frames.append(bytes(frame_bytes))

lengths = sorted(set(black_counts) | set(white_counts))

black_values = [black_counts.get(length, 0) for length in lengths]
white_values = [white_counts.get(length, 0) for length in lengths]

fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)

axes[0].bar(lengths, black_values, color="black")
axes[0].set_title("Black segments")
axes[0].set_xlabel("Segment length")
axes[0].set_ylabel("Number of segments")
axes[0].grid(axis="y", alpha=0.3)
axes[1].bar(lengths, white_values, color="black")
axes[1].set_title("White segments")
axes[1].set_xlabel("Segment length")
axes[1].grid(axis="y", alpha=0.3)

plt.tight_layout()
plt.savefig(OUTPUT_DIR / f"{INPUT_BASENAME}_dist.png", dpi=300, bbox_inches="tight")
plt.close()

byte_counts = {}
for frame in rle_frames:
    for b in frame:
        byte_counts[b] = byte_counts.get(b, 0) + 1

lengths = sorted(set(byte_counts))
bvals = [byte_counts.get(length, 0) for length in lengths]
fig, axes = plt.subplots(1, 1, figsize=(14, 5), sharey=True)

axes.bar(lengths, bvals, color="black")
axes.set_title("Byte distribution")
axes.set_xlabel("Value")
axes.set_ylabel("Occurances")
axes.grid(axis="y", alpha=0.3)

plt.tight_layout()
plt.savefig(OUTPUT_DIR / f"{INPUT_BASENAME}_dist2.png", dpi=300, bbox_inches="tight")
plt.close()

byte_counts = sorted(byte_counts.items(), key=lambda x: x[1], reverse=True)
print(byte_counts)

def pack_frame(frame):
    bitstream = "00001"
    prev = 0
    for b in frame:
        if b == byte_counts[0][0]:
            bitstream += "1"
        elif b == byte_counts[1][0]:
            bitstream += "01"
        elif prev == b:
            bitstream += "001"
        else:
            bitstream += "0001" + ("0"*8 + bin(b)[2:])[-8:]
        prev = b

    pad = 8 - (len(bitstream) % 8)
    if pad > 0:
        bitstream += "0" * pad

    bs = bitstream
    res_bytes = []
    while len(bitstream) > 0:
        res_bytes.append(int(bitstream[:8],2))
        bitstream = bitstream[8:]
    res = bytes(res_bytes)

    print(bs, res.hex())
    return res

print(rle_frames[0].hex())

bytes_per_frame = []
for x in range(len(rle_frames)):
    rle_frames[x] = pack_frame(rle_frames[x])
    bytes_per_frame.append(len(rle_frames[x]))

print(f"{len(blocks_per_frame)} frames, MAX RPF: {max(blocks_per_frame)}, MIN RPF: {min(blocks_per_frame)}, AVG RPF: {np.average(blocks_per_frame)}")
print(f"{len(bytes_per_frame)} frames, MAX BPF: {max(bytes_per_frame)}, MIN BPF: {min(bytes_per_frame)}, AVG BPF: {np.average(bytes_per_frame)}")
print(f"FPS={VIDEO_FPS}")

FRAME_TIME_MS = 1000 / VIDEO_FPS
FRAME_TIME_DMS = round(FRAME_TIME_MS * 10)
rle_frames[0] = bytes([
    0xA5, # preamble, no frame can start with A5 other than this
    0x02, # number of coded bytes (always 2 lol; nobody will ever use this script)
    byte_counts[0][0],
    byte_counts[1][0],
    (FRAME_TIME_DMS>>8)&0xFF,
    FRAME_TIME_DMS&0xFF,
]) + rle_frames[0]

with open(OUTPUT_DIR / f"{INPUT_BASENAME}.mdslot", "wb") as wf:
    wf.write(b"MDSLOT\0\0") # magic+version
    wf.write(b"\0\0\0") # placeholder for n_slots
    with open(OUTPUT_DIR / f"{INPUT_BASENAME}.oma", "rb") as f:
        f.seek(0x60)
        cluster = 0x031
        sector = 0
        agroup = 0
        slots = 0
        wf.write(bytes([(cluster >> 8)&0xff, cluster&0xff, sector])) # start address

        # reserved area padding so track start is clean and has continous EFM
        for _ in range(32):
            wf.write(bytes([(cluster >> 8)&0xff, cluster&0xff, sector, 0x02]) + bytes([0]*(0x920-4)))
            sector += 1
            if sector == 32:
                sector = 0
                cluster += 1
            slots += 1

        sector_data = bytes([(cluster >> 8)&0xff, cluster&0xff, sector, 0x02])
        
        playtime = 0
        frametime = 0

        frame_idx = 0
        frame_ofs = 0

        SOUND_BLOCK_SIZE_MS = 23.2/2
        # >36 for none to be late for bad apple
        MAX_AHEAD_FRAMES = 40

        while block := f.read(192):
            # sadly we can't put bytes here as it fucks with the decoder, at least in Sharp land
            preamble = b"\xAC\0\0\0\0\0\0\0\0\0\0\0"
            sector_data += preamble + block

            rle_payload = []
            for k in range(8):
                # add zeros if we are ahead by too much
                if frame_idx >= len(rle_frames) or (frame_ofs == 0 and frame_idx - MAX_AHEAD_FRAMES > playtime / FRAME_TIME_MS):
                    rle_payload.append(0x00)
                    continue
                frame = rle_frames[frame_idx]
                rle_payload.append(frame[frame_ofs])
                frame_ofs += 1
                if frame_ofs >= len(frame):
                    frame_ofs = 0
                    frame_idx += 1
                    frametime += FRAME_TIME_MS

            sector_data += bytes(rle_payload)
            print(f"{playtime:6.1f} {frametime:6.1f} {'BEHIND' if frametime < playtime else 'AHEAD '} {int(abs(frametime-playtime)/FRAME_TIME_MS)} frames")
            playtime += SOUND_BLOCK_SIZE_MS

            agroup += 1
            if agroup == 11:
                agroup = 0
                sector += 1
                if sector == 32:
                    sector = 0
                    cluster += 1
                wf.write(sector_data)
                slots += 1
                sector_data = bytes([(cluster >> 8)&0xff, cluster&0xff, sector, 0x02])

    wf.seek(8)
    wf.write(bytes([(slots>>16)&0xFF,(slots>>8)&0xFF,slots&0xFF]))

track_end = cluster, sector, agroup

def pack_md_address(c,s,g):
    cc = c >> 6
    cs = ((s >> 4) & 3) | (c << 2)
    sg = g | (s << 4)
    return cc&0xff, cs&0xff, sg&0xff

# build bare minimum UTOC
with open(OUTPUT_DIR / f"{INPUT_BASENAME}_toc.mdslot", "wb") as wf:
    wf.write(b"MDSLOT\0\0") # magic+version
    slots = 3*32
    wf.write(bytes([(slots>>16)&0xFF,(slots>>8)&0xFF,slots&0xFF]))
    cluster = 0x003
    sector = 0
    agroup = 0
    wf.write(bytes([(cluster >> 8)&0xff, cluster&0xff, sector])) # start address

    for _ in range(3):
        sector = 0
        sector_data = bytes([(cluster >> 8)&0xff, cluster&0xff, sector, 0x02])
        # hand build a minimal address sector
        payload = [0]*(0x920-4)
        # make/model
        payload[8] = 0x20
        payload[9] = 0x01
        
        payload[10] = 1 # first tno
        payload[11] = 1 # n_tracks
        payload[15] = 1 # only address sector is present
        payload[27] = 0 # p_empty
        payload[28] = 255 # p_fra
        payload[29] = 1 # p_tno1

        descriptor_area = 0x120-4

        # descriptor
        idx = descriptor_area+(1*8)
        cc, cs, sg = pack_md_address(0x032, 0, 0)
        payload[idx+0] = cc
        payload[idx+1] = cs
        payload[idx+2] = sg
        payload[idx+3] = 0x02 | 0x40 | 0x80 # LP2, not protected
        cc, cs, sg = pack_md_address(*track_end)
        payload[idx+4] = cc
        payload[idx+5] = cs
        payload[idx+6] = sg
        payload[idx+7] = 0 # no link

        # free area (for a 74min disc)
        idx = descriptor_area+(255*8)
        cc, cs, sg = pack_md_address(track_end[0]+1, 0, 0)
        payload[idx+0] = cc
        payload[idx+1] = cs
        payload[idx+2] = sg
        payload[idx+3] = 0
        cc, cs, sg = pack_md_address(0x08CB, 0, 0)
        payload[idx+4] = cc
        payload[idx+5] = cs
        payload[idx+6] = sg
        payload[idx+7] = 0 # no link

        # this is wrong, but whatever
        p = 254
        for x in range(253):
            so = descriptor_area + (x+2)*8
            payload[so+7] = p
            p -= 1

        sector_data += bytes(payload)
        wf.write(sector_data)
        sector += 1

        for _ in range(31):
            sector_data = bytes([(cluster >> 8)&0xff, cluster&0xff, sector, 0x02])
            sector_data += bytes([0]*(0x920-4))
            sector += 1
            wf.write(sector_data)
        cluster += 1
