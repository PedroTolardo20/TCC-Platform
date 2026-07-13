# rav_vision

Pacote ROS 2 Humble para treinar e validar datasets de deteccao de objetos usando Ultralytics YOLO26.

## Estrutura

```bash
rav_vision/
├── config/
│   ├── rav_dataset.yaml
│   ├── train_params.yaml
│   └── val_params.yaml
├── datasets/
│   └── rav_dataset/
│       ├── data.yaml
│       ├── images/
│       │   ├── train/
│       │   ├── val/
│       │   └── test/
│       └── labels/
│           ├── train/
│           ├── val/
│           └── test/
├── launch/
│   ├── train_yolo26.launch.py
│   └── val_yolo26.launch.py
├── rav_vision/
│   ├── dataset_check.py
│   ├── train_yolo26.py
│   ├── val_yolo26.py
│   └── yolo26_common.py
├── scripts/
│   └── create_dataset_dirs.sh
├── package.xml
├── setup.cfg
├── setup.py
└── requirements.txt
```

## Instalar no workspace

Assumindo que seu workspace esta em `~/TCC-Platform/robotics_ws`:

```bash
cd ~/TCC-Platform/robotics_ws/src
# coloque a pasta rav_vision aqui

cd ~/TCC-Platform/robotics_ws
python3 -m pip install --user -U pip
python3 -m pip install --user -r src/rav_vision/requirements.txt

rosdep install --from-paths src --ignore-src -r -y
colcon build --packages-select rav_vision
source install/setup.bash
```

## Preparar dataset

O dataset deve seguir o formato YOLO:

```bash
src/rav_vision/datasets/rav_dataset/
├── images/train/*.jpg|png
├── images/val/*.jpg|png
├── images/test/*.jpg|png       # opcional
├── labels/train/*.txt
├── labels/val/*.txt
└── labels/test/*.txt           # opcional
```

Cada `.txt` precisa ter o mesmo nome da imagem correspondente e linhas neste formato:

```txt
classe x_centro y_centro largura altura
```

Os valores `x_centro`, `y_centro`, `largura` e `altura` devem estar normalizados entre 0 e 1.

Edite as classes em:

```bash
src/rav_vision/config/rav_dataset.yaml
```

Exemplo:

```yaml
names:
  0: celular
  1: carregador
  2: fone
```

## Conferir dataset

```bash
cd ~/TCC-Platform/robotics_ws
source install/setup.bash
ros2 run rav_vision rav_dataset_check --data src/rav_vision/config/rav_dataset.yaml
```

## Treinar YOLO26

Treino padrao usando `yolo26n.pt`:

```bash
ros2 run rav_vision yolo26_train \
  --data src/rav_vision/config/rav_dataset.yaml \
  --model yolo26n.pt \
  --epochs 100 \
  --imgsz 640 \
  --batch 8 \
  --device 0
```

Tambem pode rodar por launch:

```bash
ros2 launch rav_vision train_yolo26.launch.py \
  data:=src/rav_vision/config/rav_dataset.yaml \
  model:=yolo26n.pt \
  epochs:=100 \
  imgsz:=640 \
  batch:=8 \
  device:=0
```

O melhor peso fica em:

```bash
runs/rav_vision/train/yolo26_rav/weights/best.pt
```

## Validar o modelo treinado

```bash
ros2 run rav_vision yolo26_val \
  --data src/rav_vision/config/rav_dataset.yaml \
  --model runs/rav_vision/train/yolo26_rav/weights/best.pt \
  --imgsz 640 \
  --batch 8 \
  --device 0
```

Ou por launch:

```bash
ros2 launch rav_vision val_yolo26.launch.py \
  data:=src/rav_vision/config/rav_dataset.yaml \
  model:=runs/rav_vision/train/yolo26_rav/weights/best.pt \
  imgsz:=640 \
  batch:=8 \
  device:=0
```

## Observacoes

- Use `--device cpu` se nao tiver GPU configurada.
- Comece com `yolo26n.pt` para testar rapido. Depois use `yolo26s.pt` ou maior se quiser mais acuracia.
- Os resultados do treino e validacao sao salvos em `runs/rav_vision/`.
