from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.descriptions import ParameterValue
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_rav_description = FindPackageShare("rav_description")
    pkg_nav2 = FindPackageShare("nav2_bringup")

    xacro_file = PathJoinSubstitution(
        [pkg_rav_description, "urdf", "platform_with_mesh_and_wheels.urdf.xacro"]
    )

    rviz_config = PathJoinSubstitution(
        [pkg_rav_description, "rviz2", "rav_nav.rviz"]
    )

    map_file = PathJoinSubstitution(
        [pkg_rav_description, "maps", "test_map.yaml"]
    )

    nav2_params = PathJoinSubstitution(
        [pkg_rav_description, "config", "nav2_params.yaml"]
    )

    nav2_launch = PathJoinSubstitution(
        [pkg_nav2, "launch", "navigation_launch.py"]
    )

    robot_description = ParameterValue(
        Command(["xacro", " ", xacro_file]),
        value_type=str
    )

    return LaunchDescription([
        SetEnvironmentVariable("RMW_IMPLEMENTATION", "rmw_cyclonedds_cpp"),

        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            name="robot_state_publisher",
            output="screen",
            parameters=[{"robot_description": robot_description}],
        ),

        Node(
            package="joint_state_publisher",
            executable="joint_state_publisher",
            name="joint_state_publisher",
            output="screen",
        ),

        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name="map_to_odom_broadcaster",
            arguments=["0", "0", "0", "0", "0", "0", "map", "odom"],
            output="screen",
        ),

        Node(
            package="rav_platform_ctrl",
            executable="platform_ctrl",
            name="rav_platform_ctrl",
            output="screen",
        ),

        Node(
            package="nav2_map_server",
            executable="map_server",
            name="map_server",
            output="screen",
            parameters=[{
                "use_sim_time": False,
                "yaml_filename": map_file,
            }],
        ),

        Node(
            package="nav2_lifecycle_manager",
            executable="lifecycle_manager",
            name="lifecycle_manager_map",
            output="screen",
            parameters=[{
                "use_sim_time": False,
                "autostart": True,
                "node_names": ["map_server"],
            }],
        ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(nav2_launch),
            launch_arguments={
                "use_sim_time": "false",
                "map": map_file,
                "params_file": nav2_params,
            }.items(),
        ),

        Node(
            package="rviz2",
            executable="rviz2",
            name="rviz2",
            arguments=["-d", rviz_config],
            output="screen",
        ),
    ])