from pathlib import Path

import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def generate_launch_description():
    sim_share = Path(
        get_package_share_directory("rav_manipulation_sim")
    )

    moveit_share = Path(
        get_package_share_directory(
            "rav_manipulator_moveit_config"
        )
    )

    robot_xacro = (
        sim_share
        / "urdf"
        / "rav_manipulator_gazebo.urdf.xacro"
    )

    semantic_file = (
        sim_share
        / "config"
        / "rav_gazebo.srdf"
    )

    kinematics_file = (
        sim_share
        / "config"
        / "rav_physics_kinematics.yaml"
    )

    rviz_file = (
        sim_share
        / "config"
        / "rav_gazebo_moveit.rviz"
    )

    moveit_controllers_file = (
        moveit_share
        / "config"
        / "moveit_controllers.yaml"
    )

    moveit_config = (
        MoveItConfigsBuilder(
            "rav_manipulator",
            package_name="rav_manipulator_moveit_config",
        )
        .robot_description(
            file_path=str(robot_xacro)
        )
        .robot_description_semantic(
            file_path=str(semantic_file)
        )
        .robot_description_kinematics(
            file_path=str(kinematics_file)
        )
        .joint_limits()
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

    moveit_controllers = {
        "moveit_controller_manager": (
            "moveit_simple_controller_manager/"
            "MoveItSimpleControllerManager"
        ),
        "moveit_simple_controller_manager": load_yaml(
            moveit_controllers_file
        ),
    }

    trajectory_execution = {
        "moveit_manage_controllers": False,
        "trajectory_execution.execution_duration_monitoring": False,
        "trajectory_execution.allowed_execution_duration_scaling": 5.0,
        "trajectory_execution.allowed_goal_duration_margin": 3.0,
        "trajectory_execution.allowed_start_tolerance": 0.05,
    }

    move_group = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            moveit_config.to_dict(),
            moveit_controllers,
            trajectory_execution,
            {"use_sim_time": True},
        ],
    )

    rviz = Node(
        package="rviz2",
        executable="rviz2",
        output="screen",
        arguments=[
            "-d",
            str(rviz_file),
        ],
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            {"use_sim_time": True},
        ],
    )

    return LaunchDescription([
        move_group,
        rviz,
    ])
