#!/bin/zsh
set -euo pipefail

project_root="${0:A:h:h}"
output_dir="$project_root/output/audio"
source_aiff="$output_dir/tsukuyomi-rms-demo.aiff"
output_wav="$output_dir/tsukuyomi-rms-demo.wav"

mkdir -p "$output_dir"

say \
  -v Kyoko \
  -r 165 \
  -o "$source_aiff" \
  "こんばんは。月詠ねむりです。これは、音声に合わせて表情と口を動かすテストです。"

ffmpeg \
  -hide_banner \
  -loglevel error \
  -y \
  -i "$source_aiff" \
  -ac 1 \
  -ar 48000 \
  -c:a pcm_s16le \
  "$output_wav"

rm "$source_aiff"
echo "$output_wav"
