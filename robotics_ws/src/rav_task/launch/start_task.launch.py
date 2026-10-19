"""Sobe só o orquestrador start_task. Rodar depois de start_devices.launch.py
já estar de pé (câmera, visão, MoveIt, manipulator_node, vision_pick_bridge).
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    port_arg = DeclareLaunchArgument(
        "port", default_value="8766",
        description="Porta do servidor WebSocket que o RavPlatform conecta.",
    )
    place_x_arg = DeclareLaunchArgument(
        "place_x", default_value="0.0",
        description="X (frame manipulator_world) do ponto de entrega -- calibrar.",
    )
    place_y_arg = DeclareLaunchArgument(
        "place_y", default_value="0.0",
        description="Y (frame manipulator_world) do ponto de entrega -- calibrar.",
    )
    cam_pose_settle_arg = DeclareLaunchArgument(
        "cam_pose_settle_s", default_value="1.5",
        description="Segundos de espera em cam_pose antes de confiar na detecção.",
    )

    align_tolerance_arg = DeclareLaunchArgument(
        "align_tolerance_m", default_value="0.02",
        description="Gira a base enquanto |x| da detecção passar disso (m).",
    )
    base_axis_offset_arg = DeclareLaunchArgument(
        "base_axis_offset_m", default_value="0.0",
        description="Distância do eixo de giro do Temi até manipulator_world, "
                    "na direção de alcance do braço (m) -- medir.",
    )
    turn_sign_arg = DeclareLaunchArgument(
        "turn_sign", default_value="1",
        description="1 ou -1: inverte o sentido do giro se a base girar pro lado errado.",
    )

    start_task = Node(
        package="rav_task",
        executable="start_task",
        output="screen",
        parameters=[{
            "port": LaunchConfiguration("port"),
            "place_x": LaunchConfiguration("place_x"),
            "place_y": LaunchConfiguration("place_y"),
            "cam_pose_settle_s": LaunchConfiguration("cam_pose_settle_s"),
            "align_tolerance_m": LaunchConfiguration("align_tolerance_m"),
            "base_axis_offset_m": LaunchConfiguration("base_axis_offset_m"),
            "turn_sign": LaunchConfiguration("turn_sign"),
        }],
    )

    return LaunchDescription([
        port_arg,
        place_x_arg,
        place_y_arg,
        cam_pose_settle_arg,
        align_tolerance_arg,
        base_axis_offset_arg,
        turn_sign_arg,
        start_task,
    ])
