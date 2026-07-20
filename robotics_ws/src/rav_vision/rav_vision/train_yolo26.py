"""Console script: ros2 run rav_vision yolo26_train."""

from __future__ import annotations

import argparse
from pathlib import Path

from rav_vision.yolo26_common import check_dataset_yaml, default_data_yaml, print_kv, resolve_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Treina um modelo Ultralytics YOLO26 usando um dataset em formato YOLO."
    )
    parser.add_argument("--data", type=str, default=None, help="Caminho para o data.yaml do dataset.")
    parser.add_argument("--model", type=str, default="yolo26n.pt", help="Modelo base: yolo26n.pt, yolo26s.pt, etc.")
    parser.add_argument("--epochs", type=int, default=100, help="Numero de epocas de treinamento.")
    parser.add_argument("--imgsz", type=int, default=640, help="Tamanho da imagem usado pelo YOLO.")
    parser.add_argument("--batch", type=int, default=8, help="Batch size. Use -1 para autobatch, se suportado.")
    parser.add_argument("--device", type=str, default="0", help="Dispositivo: 0, 0,1, cpu, mps, etc.")
    parser.add_argument("--workers", type=int, default=4, help="Numero de workers do dataloader.")
    parser.add_argument("--patience", type=int, default=50, help="Early stopping patience.")
    parser.add_argument("--project", type=str, default="runs/rav_vision/train", help="Pasta onde salvar os resultados.")
    parser.add_argument("--name", type=str, default="yolo26_rav", help="Nome da rodada de treino.")
    parser.add_argument("--resume", action="store_true", help="Continua o treino anterior, se possivel.")
    parser.add_argument("--cache", action="store_true", help="Carrega imagens em cache para acelerar treino.")
    parser.add_argument("--exist-ok", action="store_true", help="Permite sobrescrever/usar pasta ja existente.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    data_yaml = resolve_path(args.data, default_data_yaml())
    check_dataset_yaml(data_yaml)

    print_kv(
        "rav_vision | treino YOLO26",
        [
            ("data", data_yaml),
            ("model", args.model),
            ("epochs", args.epochs),
            ("imgsz", args.imgsz),
            ("batch", args.batch),
            ("device", args.device),
            ("project", Path(args.project).resolve()),
            ("name", args.name),
        ],
    )

    from ultralytics import YOLO

    model = YOLO(args.model)
    results = model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        patience=args.patience,
        project=args.project,
        name=args.name,
        resume=args.resume,
        cache=args.cache,
        exist_ok=args.exist_ok,
    )

    print("\nTreinamento finalizado.")
    print(f"Resultados salvos em: {Path(args.project).resolve() / args.name}")
    print(f"Objeto de resultados Ultralytics: {results}")


if __name__ == "__main__":
    main()
