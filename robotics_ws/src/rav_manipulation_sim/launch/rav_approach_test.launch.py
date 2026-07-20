from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    sim_share = Path(
        get_package_share_directory("rav_manipulation_sim")
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
        .to_moveit_configs()
    )

    approach_node = Node(
        package="rav_manipulation_sim",
        executable="vision_pose_to_moveit",
        name="rav_safe_approach",
        output="screen",
        parameters=[
            moveit_config.to_dict(),
            {
                "use_sim_time": True,
                "object_topic": "/rav_vision/target_pose",
                "group_name": "rav_arm",
                "tcp_link": "wrist_link",
                "approach_offset_z": 0.10,
                "execute_motion": False,
                "one_shot": True,
                "planning_time": 10.0,
                "position_tolerance": 0.02,
                "velocity_scale": 0.10,
                "acceleration_scale": 0.10,
            },
        ],
    )

    return LaunchDescription([
        approach_node,
    ])
