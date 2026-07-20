from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory

import os


def generate_launch_description():
    package_share = get_package_share_directory('mycobot_pro600_description')
    default_xacro = os.path.join(package_share, 'urdf', 'pro600_official_assets.urdf.xacro')
    default_rviz = os.path.join(package_share, 'rviz', 'pro600.rviz')

    model = LaunchConfiguration('model')
    use_rviz = LaunchConfiguration('use_rviz')
    use_joint_state_gui = LaunchConfiguration('use_joint_state_gui')

    robot_description = ParameterValue(
        Command(['xacro', ' ', model, ' ', 'use_ros2_control:=false']),
        value_type=str,
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'model',
            default_value=default_xacro,
            description='要加载的 xacro/urdf 文件路径。',
        ),
        DeclareLaunchArgument(
            'use_rviz',
            default_value='true',
            description='是否同时启动 RViz2。',
        ),
        DeclareLaunchArgument(
            'use_joint_state_gui',
            default_value='true',
            description='是否启动关节滑块。',
        ),
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            output='screen',
            parameters=[{'robot_description': robot_description}],
        ),
        Node(
            package='joint_state_publisher_gui',
            executable='joint_state_publisher_gui',
            output='screen',
            condition=IfCondition(use_joint_state_gui),
        ),
        Node(
            package='rviz2',
            executable='rviz2',
            output='screen',
            arguments=['-d', default_rviz],
            condition=IfCondition(use_rviz),
        ),
    ])
