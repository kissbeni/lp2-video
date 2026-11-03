#!/bin/bash

(uv run proc.py local/ba.avi | tee local/encode.log) || exit 1

gcc -o decode.elf decode.c && ./decode.elf > local/decode.log
