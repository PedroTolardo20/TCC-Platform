"""Funcoes auxiliares para treino/validacao YOLO26 no pacote rav_vision."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable, Optional

import yaml


def workspace_root_guess() -> Path:
    """Retorna uma tentativa de raiz do workspace a partir do diretorio atual."""
    cwd = Path.cwd().resolve()
    if cwd.name == "src":
        return cwd.parent
    if (cwd / "src").exists():
        return cwd
    # Caso esteja dentro de src/rav_vision ou outro subdiretorios
    for parent in [cwd, *cwd.parents]:
        if (parent / "src").exists():
            return parent
    return cwd


def default_data_yaml() -> Optional[Path]:
    """Procura o arquivo de dataset YAML em lugares comuns."""
    env_path = os.getenv("RAV_DATA_YAML")
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path))

    ws = workspace_root_guess()
    candidates.extend(
        [
            ws / "src" / "rav_vision" / "config" / "rav_dataset.yaml",
            ws / "src" / "rav_vision" / "datasets" / "rav_dataset" / "data.yaml",
            Path.cwd() / "config" / "rav_dataset.yaml",
            Path.cwd() / "datasets" / "rav_dataset" / "data.yaml",
        ]
    )

    try:
        from ament_index_python.packages import get_package_share_directory

        share = Path(get_package_share_directory("rav_vision"))
        candidates.append(share / "config" / "rav_dataset.yaml")
    except Exception:
        pass

    for candidate in candidates:
        candidate = candidate.expanduser().resolve()
        if candidate.exists():
            return candidate
    return None


def resolve_path(path_value: Optional[str], default: Optional[Path] = None) -> Path:
    """Resolve caminho recebido por argumento ou usa default."""
    if path_value:
        return Path(path_value).expanduser().resolve()
    if default is not None:
        return default.expanduser().resolve()
    raise FileNotFoundError("Caminho nao informado e nenhum padrao foi encontrado.")


def check_dataset_yaml(data_yaml: Path) -> dict:
    """Valida o YAML de dataset no formato esperado pelo Ultralytics."""
    if not data_yaml.exists():
        raise FileNotFoundError(
            f"Arquivo de dataset nao encontrado: {data_yaml}\n"
            "Informe com --data /caminho/para/data.yaml ou defina RAV_DATA_YAML."
        )

    with data_yaml.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    required = ["train", "val", "names"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(
            f"O arquivo {data_yaml} esta incompleto. Faltando campos: {missing}. "
            "Esperado: path, train, val e names."
        )

    names = data.get("names")
    if not isinstance(names, (list, dict)) or len(names) == 0:
        raise ValueError("O campo 'names' precisa conter ao menos uma classe.")

    return data


def print_kv(title: str, items: Iterable[tuple[str, object]]) -> None:
    """Imprime configuracoes de forma simples no terminal."""
    print(f"\n[{title}]")
    for key, value in items:
        print(f"  {key}: {value}")
    sys.stdout.flush()
