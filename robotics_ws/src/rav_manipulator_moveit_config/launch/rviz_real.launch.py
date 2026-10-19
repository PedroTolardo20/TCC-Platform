"""Abre só o RViz, com a mesma config do demo_dynamixel_real.launch.py.

Pra reabrir o RViz sem reiniciar o braço (move_group já rodando). O
moveit_rviz.launch.py gerado pelo Setup Assistant carrega outro URDF
(config/rav_manipulator.urdf.xacro), por isso este existe.
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    package_share = Path(get_package_share_directory("rav_manipulator_moveit_config"))
    description_share = Path(get_package_share_directory("rav_description"))

    moveit_config = (
        MoveItConfigsBuilder("rav_manipulator", package_name="rav_manipulator_moveit_config")
        .robot_description(
            file_path=str(description_share / "urdf" / "rav_manipulator.urdf.xacro"),
            mappings={"standalone": "true", "hardware_mode": "real"},
        )
        .to_moveit_configs()
    )

    return LaunchDescription([
        Node(
            package="rviz2",
            executable="rviz2",
            output="screen",
            arguments=["-d", str(package_share / "config" / "moveit.rviz")],
            parameters=[
                moveit_config.robot_description,
                moveit_config.robot_description_semantic,
                moveit_config.robot_description_kinematics,
            ],
        )
    ])
