"""Sobe tudo que o start_task precisa já rodando: câmera, visão 3D,
braço/gripper (MoveIt + manipulator_node) e o vision_pick_bridge.

Roda isso primeiro (uma vez, manual, no terminal do robô); só depois sobe
o start_task.launch.py.
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import AnyLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    astra_share = Path(get_package_share_directory("astra_camera"))
    manipulator_share = Path(get_package_share_directory("rav_manipulator_moveit_config"))

    model_path_arg = DeclareLaunchArgument(
        "model_path",
        # Modelo não é instalado no share/ (fica só na árvore de fontes) --
        # mesmo caminho absoluto já usado em run_vision_test.sh.
        default_value="/home/nathan/rav/robotics_ws/src/rav_vision/models/best_50epochs.pt",
        description="Caminho do .pt treinado (YOLO26) usado pelo realtime_3d_inference.",
    )

    camera = IncludeLaunchDescription(
        AnyLaunchDescriptionSource(
            str(astra_share / "launch" / "dabai_dcw.launch.xml")
        ),
        launch_arguments={"depth_registration": "true"}.items(),
    )

    manipulador = IncludeLaunchDescription(
        AnyLaunchDescriptionSource(
            str(manipulator_share / "launch" / "demo_dynamixel_real.launch.py")
        )
    )

    visao_3d = Node(
        package="rav_vision",
        executable="realtime_3d_inference",
        output="screen",
        parameters=[{
            "model_path": LaunchConfiguration("model_path"),
            "target_frame": "manipulator_world",
            "device": "cpu",
        }],
    )

    vision_pick_bridge = Node(
        package="rav_vision",
        executable="vision_pick_bridge",
        output="screen",
    )

    return LaunchDescription([
        model_path_arg,
        camera,
        manipulador,
        visao_3d,
        vision_pick_bridge,
    ])
