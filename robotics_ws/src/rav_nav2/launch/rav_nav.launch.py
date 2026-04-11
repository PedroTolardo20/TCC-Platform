from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    pkg_rav_nav2 = get_package_share_directory('rav_nav2')
    pkg_nav2_bringup = get_package_share_directory('nav2_bringup')

    use_rviz = LaunchConfiguration('use_rviz')
    use_sim_time = LaunchConfiguration('use_sim_time')
    rviz_config = LaunchConfiguration('rviz_config')

    map_file = os.path.join(
        pkg_rav_nav2,
        'maps',
        'test_map.yaml'
    )

    params_file = os.path.join(
        pkg_rav_nav2,
        'config',
        'nav2_params.yaml'
    )

    default_rviz_config = os.path.join(
        pkg_rav_nav2,
        'rviz',
        'nav2_config.rviz'
    )

    nav2_bringup_launch = os.path.join(
        pkg_nav2_bringup,
        'launch',
        'navigation_launch.py'
    )

    declare_use_rviz = DeclareLaunchArgument(
        'use_rviz',
        default_value='false',
        description='Abre o RViz da navegacao'
    )

    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Usa tempo de simulacao'
    )

    declare_rviz_config = DeclareLaunchArgument(
        'rviz_config',
        default_value=default_rviz_config,
        description='Caminho do arquivo .rviz da navegacao'
    )

    static_map_to_odom = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='static_map_to_odom',
        output='screen',
        arguments=['0', '0', '0', '0', '0', '0', 'map', 'odom']
    )

    map_server_node = Node(
        package='nav2_map_server',
        executable='map_server',
        name='map_server',
        output='screen',
        parameters=[
            {'use_sim_time': use_sim_time},
            {'yaml_filename': map_file}
        ]
    )

    lifecycle_manager_node = Node(
        package='nav2_lifecycle_manager',
        executable='lifecycle_manager',
        name='lifecycle_manager_localization',
        output='screen',
        parameters=[{
            'use_sim_time': use_sim_time,
            'autostart': True,
            'node_names': ['map_server']
        }]
    )

    nav2_navigation_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(nav2_bringup_launch),
        launch_arguments={
            'use_sim_time': use_sim_time,
            'params_file': params_file
        }.items()
    )

    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2_nav',
        output='screen',
        condition=IfCondition(use_rviz),
        arguments=['-d', rviz_config],
        parameters=[{
            'use_sim_time': use_sim_time
        }]
    )

    return LaunchDescription([
        declare_use_rviz,
        declare_use_sim_time,
        declare_rviz_config,

        static_map_to_odom,
        map_server_node,
        lifecycle_manager_node,
        nav2_navigation_launch,
        rviz_node
    ])