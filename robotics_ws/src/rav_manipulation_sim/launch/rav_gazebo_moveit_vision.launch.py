from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, RegisterEventHandler, TimerAction
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    physics_share = Path(get_package_share_directory("rav_physics_sim"))
    manipulation_share = Path(get_package_share_directory("rav_manipulation_sim"))

    real_urdf = physics_share / "urdf" / "rav_effort_real.urdf"
    physical_srdf = manipulation_share / "config" / "rav_physics.srdf"
    pick_world = manipulation_share / "worlds" / "rav_pick_world.sdf"

    robot_description = {
        "robot_description": ParameterValue(
            real_urdf.read_text(encoding="utf-8"),
            value_type=str,
        )
    }

    moveit_config = (
        MoveItConfigsBuilder(
            "rav_manipulator",
            package_name="rav_manipulator_moveit_config",
        )
        .robot_description(file_path=str(real_urdf))
        .robot_description_semantic(file_path=str(physical_srdf))
        .robot_description_kinematics(
            file_path=str(
                manipulation_share / "config" / "rav_physics_kinematics.yaml"
            )
        )
        .joint_limits()
        .planning_pipelines(
            default_planning_pipeline="ompl",
            pipelines=["ompl"],
            load_all=False,
        )
        .trajectory_execution(
            file_path="config/moveit_controllers.yaml",
            moveit_manage_controllers=False,
        )
        .planning_scene_monitor(
            publish_planning_scene=True,
            publish_geometry_updates=True,
            publish_state_updates=True,
            publish_transforms_updates=True,
            publish_robot_description=True,
            publish_robot_description_semantic=True,
        )
        .to_moveit_configs()
    )

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            [
                str(
                    Path(get_package_share_directory("ros_gz_sim"))
                    / "launch"
                    / "gz_sim.launch.py"
                )
            ]
        ),
        launch_arguments={
            "gz_args": f"-r -v 1 {pick_world}",
        }.items(),
    )

    clock_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        output="screen",
        arguments=["/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock"],
    )

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        output="screen",
        parameters=[robot_description, {"use_sim_time": True}],
    )

    spawn_robot = Node(
        package="ros_gz_sim",
        executable="create",
        output="screen",
        arguments=[
            "-topic", "robot_description",
            "-name", "rav_real_physics_arm",
            "-allow_renaming", "false",
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

    move_group = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            moveit_config.to_dict(),
            {
                "use_sim_time": True,
                "trajectory_execution.allowed_execution_duration_scaling": 2.0,
                "trajectory_execution.allowed_goal_duration_margin": 2.0,
                "trajectory_execution.allowed_start_tolerance": 0.10,
            },
        ],
    )

    perception_to_moveit = Node(
        package="rav_manipulation_sim",
        executable="vision_pose_to_moveit",
        output="screen",
        parameters=[moveit_config.to_dict(), {"use_sim_time": True}],
    )

    return LaunchDescription(
        [
            gazebo,
            clock_bridge,
            robot_state_publisher,
            spawn_robot,
            RegisterEventHandler(
                OnProcessExit(
                    target_action=spawn_robot,
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
            TimerAction(period=8.0, actions=[move_group]),
            TimerAction(period=12.0, actions=[perception_to_moveit]),
        ]
    )
