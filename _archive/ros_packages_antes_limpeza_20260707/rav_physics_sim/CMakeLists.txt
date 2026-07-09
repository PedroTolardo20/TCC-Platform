cmake_minimum_required(VERSION 3.8)
project(rav_physics_sim)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY launch urdf config
  DESTINATION share/${PROJECT_NAME}
)

install(
  PROGRAMS scripts/send_home_goal.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()
