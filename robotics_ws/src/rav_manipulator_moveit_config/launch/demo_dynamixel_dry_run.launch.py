"""MoveIt demo that executes through ros2_control mock hardware.

The only temporary part is the hardware plugin declared in the URDF
(mock_components/GenericSystem).  MoveIt still talks to the same
FollowJointTrajectory action that will be kept for OpenCM 485 EXP hardware.
"""

import os
import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import RegisterEventHandler
from launch.event_handlers import OnProcessExit
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def generate_launch_description():
    package_share = get_package_share_directory("rav_manipulator_moveit_config")

    ros2_controllers_path = os.path.join(
        package_share, "config", "ros2_controllers.yaml"
    )
    moveit_controllers_path = os.path.join(
        package_share, "config", "moveit_controllers.yaml"
    )
    rviz_config = os.path.join(package_share, "config", "moveit.rviz")

    moveit_config = (
        MoveItConfigsBuilder(
            "rav_manipulator",
            package_name="rav_manipulator_moveit_config",
        )
        .robot_description(file_path="config/rav_manipulator_dynamixel_dry_run.urdf.xacro")
        .planning_pipelines(
            default_planning_pipeline="ompl",
            pipelines=["ompl"],
            load_all=False,
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

    # MoveIt controller routing: MoveIt --> FollowJointTrajectory action of
    # /arm_controller.  The action remains unchanged on real OpenCM hardware.
    moveit_controllers = {
        "moveit_controller_manager": (
            "moveit_simple_controller_manager/MoveItSimpleControllerManager"
        ),
        "moveit_simple_controller_manager": load_yaml(moveit_controllers_path),
    }

    trajectory_execution = {
        "moveit_manage_controllers": False,

        # Temporário para validar a integração MoveIt -> ros2_control.
        # No hardware real voltaremos a habilitar o monitoramento,
        # com tempos e tolerâncias calibrados.
        "trajectory_execution.execution_duration_monitoring": False,

        "trajectory_execution.allowed_execution_duration_scaling": 10.0,
        "trajectory_execution.allowed_goal_duration_margin": 5.0,
        "trajectory_execution.allowed_start_tolerance": 0.05,
    }

    static_tf = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        output="screen",
        arguments=[
            "0", "0", "0",
            "0", "0", "0",
            "world",
            "manipulator_world",
        ],
    )

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        output="screen",
        parameters=[moveit_config.robot_description],
    )

    controller_manager = Node(
        package="controller_manager",
        executable="ros2_control_node",
        output="screen",
        parameters=[moveit_config.robot_description, ros2_controllers_path],
    )

    joint_state_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        output="screen",
        arguments=[
            "joint_state_broadcaster",
            "--controller-manager", "/controller_manager",
            "--controller-manager-timeout", "60",
        ],
    )

    arm_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        output="screen",
        arguments=[
            "arm_controller",
            "--controller-manager", "/controller_manager",
            "--controller-manager-timeout", "60",
        ],
    )

    move_group = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            moveit_config.to_dict(),
            trajectory_execution,
            moveit_controllers,
        ],
    )

    # Keep RViz free of joint-limit overrides.  On this Humble installation,
    # passing that map to RViz causes a type conflict even though move_group
    # itself accepts the same planning configuration.
    rviz = Node(
        package="rviz2",
        executable="rviz2",
        output="screen",
        arguments=["-d", rviz_config],
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
        ],
    )

    start_arm_controller = RegisterEventHandler(
        OnProcessExit(
            target_action=joint_state_broadcaster_spawner,
            on_exit=[arm_controller_spawner],
        )
    )

    start_moveit = RegisterEventHandler(
        OnProcessExit(
            target_action=arm_controller_spawner,
            on_exit=[move_group, rviz],
        )
    )

    return LaunchDescription([
        static_tf,
        robot_state_publisher,
        controller_manager,
        joint_state_broadcaster_spawner,
        start_arm_controller,
        start_moveit,
    ])
