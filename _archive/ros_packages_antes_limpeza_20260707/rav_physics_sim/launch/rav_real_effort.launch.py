from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import PathJoinSubstitution


def generate_launch_description():
    package_share = Path(
        get_package_share_directory("rav_physics_sim")
    )
    urdf_path = package_share / "urdf" / "rav_effort_real.urdf"

    robot_description = {
        "robot_description": ParameterValue(
            urdf_path.read_text(encoding="utf-8"),
            value_type=str,
        )
    }

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [
                PathJoinSubstitution(
                    [
                        FindPackageShare("ros_gz_sim"),
                        "launch",
                        "gz_sim.launch.py",
                    ]
                )
            ]
        ),
        launch_arguments={
            "gz_args": "-r -v 1 empty.sdf",
        }.items(),
    )

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        output="screen",
        parameters=[
            robot_description,
            {"use_sim_time": True},
        ],
    )

    spawn = Node(
        package="ros_gz_sim",
        executable="create",
        output="screen",
        arguments=[
            "-topic",
            "robot_description",
            "-name",
            "rav_real_physics_arm",
            "-allow_renaming",
            "false",
        ],
    )

    joint_state_broadcaster = Node(
        package="controller_manager",
        executable="spawner",
        output="screen",
        arguments=["joint_state_broadcaster"],
    )

    arm_controller = Node(
        package="controller_manager",
        executable="spawner",
        output="screen",
        arguments=["arm_controller"],
    )

    send_home = Node(
        package="rav_physics_sim",
        executable="send_home_goal.py",
        output="screen",
    )

    clock_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        output="screen",
        arguments=[
            "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",
        ],
    )

    return LaunchDescription(
        [
            gazebo,
            clock_bridge,
            robot_state_publisher,
            spawn,
            RegisterEventHandler(
                OnProcessExit(
                    target_action=spawn,
                    on_exit=[joint_state_broadcaster],
                )
            ),
            RegisterEventHandler(
                OnProcessExit(
                    target_action=joint_state_broadcaster,
                    on_exit=[arm_controller],
                )
            ),
            RegisterEventHandler(
                OnProcessExit(
                    target_action=arm_controller,
                    on_exit=[send_home],
                )
            ),
        ]
    )
