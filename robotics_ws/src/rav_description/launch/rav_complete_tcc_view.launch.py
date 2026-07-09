from launch import LaunchDescription
from launch.substitutions import Command, FindExecutable, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    package_share = FindPackageShare("rav_description")
    xacro_file = PathJoinSubstitution(
        [package_share, "urdf", "rav_complete_tcc.urdf.xacro"]
    )
    rviz_config = PathJoinSubstitution(
        [package_share, "launch", "rav_complete_tcc_view.rviz"]
    )

    robot_description = ParameterValue(
        Command([FindExecutable(name="xacro"), " ", xacro_file]),
        value_type=str,
    )

    return LaunchDescription(
        [
            Node(
                package="robot_state_publisher",
                executable="robot_state_publisher",
                output="screen",
                parameters=[{"robot_description": robot_description}],
            ),
            Node(
                package="joint_state_publisher_gui",
                executable="joint_state_publisher_gui",
                output="screen",
            ),
            Node(
                package="rviz2",
                executable="rviz2",
                output="screen",
                arguments=["-d", rviz_config],
            ),
        ]
    )
