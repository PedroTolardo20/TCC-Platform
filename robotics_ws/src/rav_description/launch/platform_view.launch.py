from launch import LaunchDescription
from launch_ros.actions import Node
from launch.substitutions import Command, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue

def generate_launch_description():
    pkg_share = FindPackageShare('rav_description')

    xacro_file = PathJoinSubstitution([pkg_share, 'urdf', 'platform_with_mesh_and_wheels.urdf.xacro'])
    robot_description = ParameterValue(
        Command(['xacro ', xacro_file]),
        value_type=str
    )

    rviz_config = PathJoinSubstitution([pkg_share, 'rviz2', 'rvizinicial.rviz'])

    return LaunchDescription([
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            output='screen',
            parameters=[{'robot_description': robot_description}],
        ),

        Node(
            package='joint_state_publisher_gui',
            executable='joint_state_publisher_gui',
            output='screen',
        ),

        Node(
            package='rviz2',
            executable='rviz2',
            output='screen',
            arguments=['-d', rviz_config],
        ),
    ])
