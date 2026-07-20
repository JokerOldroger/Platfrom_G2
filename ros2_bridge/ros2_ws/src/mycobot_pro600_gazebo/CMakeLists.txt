cmake_minimum_required(VERSION 3.8)
project(mycobot_pro600_gazebo)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY launch config worlds vendor_ros1
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
