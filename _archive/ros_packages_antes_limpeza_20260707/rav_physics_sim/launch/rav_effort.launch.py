from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch.substitutions import Command, LaunchConfiguration, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    use_sim_time = LaunchConfiguration("use_sim_time")
    payload = LaunchConfiguration("payload")

    robot_description_content = Command([
        "xacro ",
        PathJoinSubstitution([
            FindPackageShare("rav_physics_sim"),
            "urdf",
            "rav_effort.urdf.xacro",
        ]),
        " payload:=",
        payload,
    ])

    robot_description = {"robot_description": ParameterValue(robot_description_content, value_type=str)}

    controllers = PathJoinSubstitution([
        FindPackageShare("rav_physics_sim"),
        "config",
        "rav_effort_controllers.yaml",
    ])

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare("ros_gz_sim"),
                "launch",
                "gz_sim.launch.py",
            ])
        ]),
        launch_arguments={
            "gz_args": "-r -v 1 empty.sdf",
        }.items(),
    )

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        output="screen",
        parameters=[robot_description, {"use_sim_time": use_sim_time}],
    )

    spawn = Node(
        package="ros_gz_sim",
        executable="create",
        output="screen",
        arguments=[
            "-topic",
            "robot_description",
            "-name",
            "rav_physics_arm",
            "-allow_renaming",
            "false",
        ],
    )

    joint_state_broadcaster = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["joint_state_broadcaster"],
        output="screen",
    )

    arm_controller = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "arm_controller",
            "--param-file",
            controllers,
        ],
        output="screen",
    )

    clock_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=["/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock"],
        output="screen",
    )

    return LaunchDescription([
        DeclareLaunchArgument("use_sim_time", default_value="true"),
        DeclareLaunchArgument(
            "payload",
            default_value="0.0",
            description="Payload mass in kg added to the 0.8 kg distal assembly.",
        ),
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
    ])
