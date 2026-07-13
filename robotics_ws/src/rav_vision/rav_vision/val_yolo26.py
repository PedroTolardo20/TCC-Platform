"""Console script: ros2 run rav_vision yolo26_val."""

from __future__ import annotations

import argparse
from pathlib import Path

from rav_vision.yolo26_common import check_dataset_yaml, default_data_yaml, print_kv, resolve_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida um modelo YOLO26 treinado usando o dataset em formato YOLO."
    )
    parser.add_argument("--data", type=str, default=None, help="Caminho para o data.yaml do dataset.")
    parser.add_argument("--model", type=str, default="runs/rav_vision/train/yolo26_rav/weights/best_50epochs.pt", help="Modelo .pt a validar.")
    parser.add_argument("--imgsz", type=int, default=640, help="Tamanho da imagem usado na validacao.")
    parser.add_argument("--batch", type=int, default=8, help="Batch size.")
    parser.add_argument("--device", type=str, default="0", help="Dispositivo: 0, cpu, etc.")
    parser.add_argument("--split", type=str, default="val", choices=["val", "test", "train"], help="Split do dataset.")
    parser.add_argument("--conf", type=float, default=0.001, help="Confianca minima para validacao.")
    parser.add_argument("--iou", type=float, default=0.7, help="IoU usado na validacao.")
    parser.add_argument("--project", type=str, default="runs/rav_vision/val", help="Pasta onde salvar os resultados.")
    parser.add_argument("--name", type=str, default="yolo26_rav_val", help="Nome da rodada de validacao.")
    parser.add_argument("--exist-ok", action="store_true", help="Permite sobrescrever/usar pasta ja existente.")
    parser.add_argument(
        "--traditional-head",
        action="store_true",
        help="Usa a cabeca one-to-many tradicional com NMS, quando suportado pelo YOLO26.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    data_yaml = resolve_path(args.data, default_data_yaml())
    check_dataset_yaml(data_yaml)
    model_path = resolve_path(args.model)

    print_kv(
        "rav_vision | validacao YOLO26",
        [
            ("data", data_yaml),
            ("model", model_path),
            ("imgsz", args.imgsz),
            ("batch", args.batch),
            ("device", args.device),
            ("split", args.split),
            ("project", Path(args.project).resolve()),
            ("name", args.name),
            ("head", "one-to-many/NMS" if args.traditional_head else "one-to-one/end2end"),
        ],
    )

    from ultralytics import YOLO

    model = YOLO(str(model_path))
    val_kwargs = dict(
        data=str(data_yaml),
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        split=args.split,
        conf=args.conf,
        iou=args.iou,
        project=args.project,
        name=args.name,
        exist_ok=args.exist_ok,
    )

    if args.traditional_head:
        val_kwargs["end2end"] = False

    try:
        metrics = model.val(**val_kwargs)
    except TypeError:
        # Mantem compatibilidade caso a versao instalada do ultralytics ainda nao aceite end2end.
        val_kwargs.pop("end2end", None)
        metrics = model.val(**val_kwargs)

    print("\nValidacao finalizada.")
    print(f"Resultados salvos em: {Path(args.project).resolve() / args.name}")
    print(f"Metricas Ultralytics: {metrics}")


if __name__ == "__main__":
    main()
