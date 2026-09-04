cmake_minimum_required(VERSION 3.8)
project(rav_manipulator_moveit_config)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(geometry_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  srv/MoveToNamedState.srv
  srv/MoveToPose.srv
  srv/Pick.srv
  srv/Place.srv
  DEPENDENCIES geometry_msgs
)

# Nao chamamos ament_python_install_package() aqui: rosidl_generate_interfaces
# ja faz isso internamente pra instalar os bindings Python dos .srv acima, e
# uma segunda chamada com o mesmo nome de projeto colide (mesmo alvo CMake).
# manipulator_node.py fica auto-contido (sem modulo Python proprio pra
# instalar) e importa rav_manipulator_moveit_config.srv normalmente, que ja
# fica disponivel via essa instalacao do rosidl.

install(
  PROGRAMS scripts/manipulator_node.py
  DESTINATION lib/${PROJECT_NAME}
)

install(
  DIRECTORY config launch
  DESTINATION share/${PROJECT_NAME}
)

install(
  FILES .setup_assistant
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
