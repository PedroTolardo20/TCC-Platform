"""Checagem simples do dataset YOLO antes de iniciar treinamento."""

from __future__ import annotations

import argparse
from pathlib import Path

from rav_vision.yolo26_common import check_dataset_yaml, default_data_yaml, resolve_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Confere a estrutura basica do dataset YOLO.")
    parser.add_argument("--data", type=str, default=None, help="Caminho para o data.yaml do dataset.")
    return parser.parse_args()


def _resolve_dataset_dir(data_yaml: Path, data: dict) -> Path:
    base = data.get("path")
    if base is None:
        return data_yaml.parent
    base_path = Path(str(base)).expanduser()
    if base_path.is_absolute():
        return base_path.resolve()
    return (data_yaml.parent / base_path).resolve()


def main() -> None:
    args = parse_args()
    data_yaml = resolve_path(args.data, default_data_yaml())
    data = check_dataset_yaml(data_yaml)
    root = _resolve_dataset_dir(data_yaml, data)

    print(f"Dataset YAML: {data_yaml}")
    print(f"Dataset root: {root}")
    print(f"Classes: {data.get('names')}")

    for split in ["train", "val", "test"]:
        if split not in data:
            continue
        images_dir = root / str(data[split])
        labels_dir = Path(str(images_dir).replace("/images/", "/labels/"))
        images = []
        if images_dir.exists():
            for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.webp"):
                images.extend(images_dir.glob(ext))
        labels = list(labels_dir.glob("*.txt")) if labels_dir.exists() else []
        print(f"{split}: {len(images)} imagens | {len(labels)} labels")
        print(f"  imagens: {images_dir} {'OK' if images_dir.exists() else 'NAO ENCONTRADO'}")
        print(f"  labels : {labels_dir} {'OK' if labels_dir.exists() else 'NAO ENCONTRADO'}")


if __name__ == "__main__":
    main()
