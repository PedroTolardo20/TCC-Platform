import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node
from moveit_configs_utils import MoveItConfigsBuilder


def generate_launch_description():
    moveit_config = (
        MoveItConfigsBuilder(
            "rav_manipulator",
            package_name="rav_manipulator_moveit_config",
        )
        .planning_pipelines(
            default_planning_pipeline="ompl",
            pipelines=["ompl"],
            load_all=False,
        )
        .trajectory_execution(
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

    package_share = get_package_share_directory(
        "rav_manipulator_moveit_config"
    )

    rviz_config = os.path.join(
        package_share,
        "config",
        "moveit.rviz",
    )

    move_group = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[moveit_config.to_dict()],
    )

    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        output="screen",
        parameters=[moveit_config.robot_description],
    )

    joint_state_publisher = Node(
        package="joint_state_publisher_gui",
        executable="joint_state_publisher_gui",
        output="screen",
        parameters=[moveit_config.robot_description],
    )

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

    return LaunchDescription([
        static_tf,
        robot_state_publisher,
        joint_state_publisher,
        move_group,
        rviz,
    ])
