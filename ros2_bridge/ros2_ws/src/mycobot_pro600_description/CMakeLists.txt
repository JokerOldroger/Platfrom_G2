cmake_minimum_required(VERSION 3.8)
project(mycobot_pro600_description)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY launch urdf rviz meshes vendor_ros1 scripts
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
