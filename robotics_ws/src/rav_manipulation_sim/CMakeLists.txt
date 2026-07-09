cmake_minimum_required(VERSION 3.8)
project(rav_manipulation_sim)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(shape_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_ros REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)
find_package(moveit_msgs REQUIRED)
find_package(moveit_ros_planning_interface REQUIRED)

add_executable(vision_pose_to_moveit src/vision_pose_to_moveit.cpp)
ament_target_dependencies(vision_pose_to_moveit
  rclcpp
  geometry_msgs
  shape_msgs
  tf2
  tf2_ros
  tf2_geometry_msgs
  moveit_msgs
  moveit_ros_planning_interface
)

add_executable(mock_vision_pose src/mock_vision_pose.cpp)
ament_target_dependencies(mock_vision_pose
  rclcpp
  geometry_msgs
)

install(TARGETS
  vision_pose_to_moveit
  mock_vision_pose
  DESTINATION lib/${PROJECT_NAME}
)

install(
  DIRECTORY launch config models worlds
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
