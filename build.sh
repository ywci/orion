#!/bin/bash

TARGET=chisel
FORMATS=("chisel" "verilog" "pymtl" "kami")
CFG=conf/env.cfg

MAX_TOKENS=0
TEMPERATURE=0
MODEL="default"

cd "$(dirname "$0")"
if [ ! -e $CFG ]; then
  echo "Error: $CFG does not exist"
  exit 1
fi

source $CFG
if [ "$API_KEY" = "" -o "$URL" = "" ]; then
  echo "Error: invalid parameters in $CFG"
  exit 1
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    -t)
    TARGET=$2
    shift 2
    ;;
    *)
    echo "usage: $0 [-g chisel|verilog|kami|pymtl]"
    exit 1
    ;;
  esac
done

if [[ "${FORMATS[@]}" =~ "$TARGET" ]]; then
    echo "Generate by $TARGET ..."
else
    echo "$TARGET is not supported!"
    exit 1
fi

python3 scripts/gen.py $MODEL $API_KEY $URL $TEMPERATURE $MAX_TOKENS $TARGET
echo "finished!"
