import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import get_package_share_directory

def generate_launch_description():
    # 1. Referências dos pacotes
    pkg_rav_description = FindPackageShare("rav_description")
    pkg_rav_nav2 = FindPackageShare("rav_nav2")
    nav2_bringup_dir = get_package_share_directory('nav2_bringup')

    # 2. Caminhos dos ficheiros (Garante que aponta para rav_nav2)
    xacro_file = PathJoinSubstitution(
        [pkg_rav_description, "urdf", "platform_with_mesh_and_wheels.urdf.xacro"]
    )

    rviz_config = PathJoinSubstitution(
        [pkg_rav_nav2, "rviz", "rav_nav.rviz"]
    )

    map_file = PathJoinSubstitution(
        [pkg_rav_nav2, "maps", "test_map.yaml"]
    )

    nav2_params = PathJoinSubstitution(
        [pkg_rav_nav2, "config", "nav2_params.yaml"]
    )

    robot_description_content = ParameterValue(
        Command(["xacro", " ", xacro_file]),
        value_type=str
    )

    return LaunchDescription([
        # Força o uso do CycloneDDS para estabilidade no mapa
        SetEnvironmentVariable("RMW_IMPLEMENTATION", "rmw_cyclonedds_cpp"),

        # --- DESCRIÇÃO E TF ---
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            name="robot_state_publisher",
            output="screen",
            parameters=[{
                "robot_description": robot_description_content,
                "use_sim_time": False
            }],
        ),

        Node(
            package="joint_state_publisher",
            executable="joint_state_publisher",
            name="joint_state_publisher",
            output="screen",
            parameters=[{"use_sim_time": False}]
        ),

        # TF Estática necessária para o Nav2 não travar sem AMCL
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name="map_to_odom_broadcaster",
            arguments=["0", "0", "0", "0", "0", "0", "map", "odom"],
            output="screen",
        ),

        # --- BRIDGE COM O TEMI ---
        Node(
            package="rav_platform_ctrl",
            executable="platform_ctrl",
            name="rav_platform_ctrl",
            output="screen",
            parameters=[{"use_sim_time": False}]
        ),

        # --- MAPA E NAVEGAÇÃO ---
        Node(
            package="nav2_map_server",
            executable="map_server",
            name="map_server",
            output="screen",
            parameters=[{
                "use_sim_time": False,
                "yaml_filename": map_file,
                "topic_name": "map",
                "frame_id": "map"
            }],
        ),

        # Gerencia o ciclo de vida: Sem isto o mapa fica em "Warn" para sempre
        Node(
            package="nav2_lifecycle_manager",
            executable="lifecycle_manager",
            name="lifecycle_manager_navigation",
            output="screen",
            parameters=[{
                "use_sim_time": False,
                "autostart": True,
                "node_names": ["map_server", "controller_server", 
                               "planner_server", "behavior_server", "bt_navigator"]
            }],
        ),

        # Motores de navegação (O que faz o robô andar de verdade)
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(nav2_bringup_dir, 'launch', 'navigation_launch.py')
            ),
            launch_arguments={
                'use_sim_time': 'false',
                'params_file': nav2_params,
                'autostart': 'true',
            }.items(),
        ),

        # --- VISUALIZAÇÃO ---
        Node(
            package="rviz2",
            executable="rviz2",
            name="rviz2",
            arguments=["-d", rviz_config],
            output="screen",
            parameters=[{"use_sim_time": False}]
        ),
    ])