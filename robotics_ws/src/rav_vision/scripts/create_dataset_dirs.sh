#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-src/rav_vision/datasets/rav_dataset}"
mkdir -p "$ROOT/images/train" "$ROOT/images/val" "$ROOT/images/test"
mkdir -p "$ROOT/labels/train" "$ROOT/labels/val" "$ROOT/labels/test"

echo "Estrutura criada em: $ROOT"
echo "Coloque as imagens em images/train e images/val."
echo "Coloque os labels .txt YOLO em labels/train e labels/val."
