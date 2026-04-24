from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration, Command, AndSubstitution, NotSubstitution
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    pkg_rav_description = get_package_share_directory('rav_description')
    pkg_rav_bringup = get_package_share_directory('rav_bringup')

    use_rviz = LaunchConfiguration('use_rviz')
    use_joint_state_publisher = LaunchConfiguration('use_joint_state_publisher')
    use_gui = LaunchConfiguration('use_gui')
    use_platform_ctrl = LaunchConfiguration('use_platform_ctrl')
    use_sim_time = LaunchConfiguration('use_sim_time')
    rviz_config = LaunchConfiguration('rviz_config')

    urdf_file = os.path.join(
        pkg_rav_description,
        'urdf',
        'rav_complete.urdf.xacro'
    )

    default_rviz_config = os.path.join(
        pkg_rav_bringup,
        'rviz',
        'bringup.rviz'
    )

    robot_description = Command([
        'xacro ',
        urdf_file
    ])

    declare_use_rviz = DeclareLaunchArgument(
        'use_rviz',
        default_value='true',
        description='Abre o RViz'
    )

    declare_use_joint_state_publisher = DeclareLaunchArgument(
        'use_joint_state_publisher',
        default_value='true',
        description='Sobe o joint_state_publisher'
    )

    declare_use_gui = DeclareLaunchArgument(
        'use_gui',
        default_value='false',
        description='Usa joint_state_publisher_gui com sliders (substitui o joint_state_publisher)'
    )

    declare_use_platform_ctrl = DeclareLaunchArgument(
        'use_platform_ctrl',
        default_value='true',
        description='Sobe o rav_platform_ctrl'
    )

    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Usa tempo de simulacao'
    )

    declare_rviz_config = DeclareLaunchArgument(
        'rviz_config',
        default_value=default_rviz_config,
        description='Caminho para o arquivo de configuracao do RViz'
    )

    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description,
            'use_sim_time': use_sim_time
        }]
    )

    # Modo normal: publica posicoes zeradas (sem GUI)
    joint_state_publisher_node = Node(
        package='joint_state_publisher',
        executable='joint_state_publisher',
        name='joint_state_publisher',
        output='screen',
        condition=IfCondition(AndSubstitution(use_joint_state_publisher, NotSubstitution(use_gui))),
        parameters=[{
            'robot_description': robot_description,
            'use_sim_time': use_sim_time
        }]
    )

    # Modo GUI: abre janela com sliders para mover os joints manualmente
    joint_state_publisher_gui_node = Node(
        package='joint_state_publisher_gui',
        executable='joint_state_publisher_gui',
        name='joint_state_publisher_gui',
        output='screen',
        condition=IfCondition(AndSubstitution(use_joint_state_publisher, use_gui)),
        parameters=[{
            'robot_description': robot_description,
            'use_sim_time': use_sim_time
        }]
    )

    platform_ctrl_node = Node(
        package='rav_platform_ctrl',
        executable='platform_ctrl',
        name='rav_platform_ctrl',
        output='screen',
        condition=IfCondition(use_platform_ctrl)
    )

    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        condition=IfCondition(use_rviz),
        arguments=['-d', rviz_config],
        parameters=[{
            'use_sim_time': use_sim_time
        }]
    )

    return LaunchDescription([
        declare_use_rviz,
        declare_use_joint_state_publisher,
        declare_use_gui,
        declare_use_platform_ctrl,
        declare_use_sim_time,
        declare_rviz_config,
        robot_state_publisher_node,
        joint_state_publisher_node,
        joint_state_publisher_gui_node,
        platform_ctrl_node,
        rviz_node,
    ])