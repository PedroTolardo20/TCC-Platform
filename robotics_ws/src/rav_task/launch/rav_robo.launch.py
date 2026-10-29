"""Sobe o robô inteiro e deixa esperando o pedido do RavTotem.

  ros2 launch rav_task rav_robo.launch.py

Sobe: braço (MoveIt + manipulator_node, sem RViz), câmera DaBai, visão 3D
(YOLO), vision_pick_bridge e o orquestrador -- que conecta no RavPlatform
(app do tablet do Temi) e espera os pedidos do RavTotem.

Antes (uma vez por boot): porta dos Dynamixel liberada
(sudo chmod 666 /dev/ttyACM0) e app RavPlatform aberto no tablet.
"""

from pathlib import Path

from ament_index_python.packages import get_package_prefix, get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, TimerAction
from launch.launch_description_sources import AnyLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    astra_share = Path(get_package_share_directory("astra_camera"))
    manipulator_share = Path(get_package_share_directory("rav_manipulator_moveit_config"))
    # O modelo não é instalado no share/: fica em src/ do workspace
    # (install/rav_vision -> install -> workspace).
    workspace = Path(get_package_prefix("rav_vision")).parent.parent
    modelo_padrao = workspace / "src" / "rav_vision" / "models" / "best_50epochs.pt"

    argumentos = [
        DeclareLaunchArgument(
            "model_path", default_value=str(modelo_padrao),
            description="Peso .pt do YOLO usado pela visão.",
        ),
        DeclareLaunchArgument(
            "temi_url", default_value="ws://172.20.10.3:8765",
            description="WebSocket do RavPlatform (tablet do Temi).",
        ),
        DeclareLaunchArgument("rviz", default_value="false"),
        DeclareLaunchArgument(
            "visualizar", default_value="true",
            description="Janela com as detecções da visão.",
        ),
    ]

    # depth_registration: profundidade alinhada à RGB. tf_publish_rate=0: TFs
    # internas da câmera em /tf_static (com /tf a 10 Hz a visão perdia a TF
    # com a CPU cheia). Nuvem de pontos e IR desligados: ninguém usa (a
    # visão lê só color + depth) e a nuvem a 30 fps deixava a câmera em ~80%
    # de um núcleo -- com a CPU cheia o YOLO caía pra ~4 s por frame.
    camera = IncludeLaunchDescription(
        AnyLaunchDescriptionSource(str(astra_share / "launch" / "dabai_dcw.launch.xml")),
        launch_arguments={
            "depth_registration": "true",
            "tf_publish_rate": "0.0",
            "enable_point_cloud": "false",
            "enable_ir": "false",
        }.items(),
    )

    braco = IncludeLaunchDescription(
        AnyLaunchDescriptionSource(
            str(manipulator_share / "launch" / "demo_dynamixel_real.launch.py")
        ),
        launch_arguments={"rviz": LaunchConfiguration("rviz")}.items(),
    )

    visao = Node(
        package="rav_vision",
        executable="realtime_3d_inference",
        output="both",
        additional_env={"PYTHONUNBUFFERED": "1"},
        parameters=[{
            "model_path": LaunchConfiguration("model_path"),
            "target_frame": "manipulator_world",
            "device": "cpu",
            "visualize": LaunchConfiguration("visualizar"),
        }],
    )

    bridge = Node(
        package="rav_vision",
        executable="vision_pick_bridge",
        output="both",
        additional_env={"PYTHONUNBUFFERED": "1"},
    )

    # Atrasado: dá tempo do move_group/manipulator_node subirem (o
    # orquestrador também espera os serviços, mas assim o log fica limpo).
    orquestrador = TimerAction(period=20.0, actions=[Node(
        package="rav_task",
        executable="orquestrador",
        output="both",
        additional_env={"PYTHONUNBUFFERED": "1"},
        parameters=[{"temi_url": LaunchConfiguration("temi_url")}],
    )])

    # output="both" + PYTHONUNBUFFERED: o log desses nós vai também, na
    # hora, pro ~/.ros/log/<data>/launch.log (os arquivos python3_*.log só
    # são escritos quando o processo fecha).
    return LaunchDescription(argumentos + [camera, braco, visao, bridge, orquestrador])
