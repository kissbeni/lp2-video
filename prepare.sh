#!/bin/bash

mkdir -p local/ && cd local/ || exit 1

if [ ! -f  ba_og.mp4 ]; then
    yt-dlp -t mp4 https://www.youtube.com/watch?v=FtutLA63Cp8 -o ba_og.mp4 || exit 1
fi

if [ ! -f ba.avi ]; then
    ffmpeg -y -i ba_og.mp4 -filter:v 'scale=32:-1' -r 10.775862069 ba.avi || exit 1
fi

if [ ! -f ba_pcm.wav ]; then
    ffmpeg -y -i ba_og.mp4 -r 44100 -c:a pcm_s16le ba_pcm.wav || exit 1
fi

if [ ! -f ba.oma ]; then
    # or use your favorite ATRAC3 encoder, whatever
    atracdenc -e atrac3 -i ba_pcm.wav -o ba.oma || exit 1
fi

echo "Input files ready."
