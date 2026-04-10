cmake_minimum_required(VERSION 3.8)
project(rav_description)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# 1. Encontrar dependências
find_package(ament_cmake REQUIRED)

# 2. Instalar arquivos e diretórios
# Isso garante que o launch, urdf e meshes vão para a pasta share do pacote
install(DIRECTORY
  launch
  urdf
  meshes
  DESTINATION share/${PROJECT_NAME}
)

# 3. Instalar o package.xml (obrigatório para o ROS2 reconhecer o pacote instalado)
install(FILES
  package.xml
  DESTINATION share/${PROJECT_NAME}
)

# 4. Testes (opcional, mantendo o seu padrão)
if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

# 5. Exportar o pacote
ament_package()