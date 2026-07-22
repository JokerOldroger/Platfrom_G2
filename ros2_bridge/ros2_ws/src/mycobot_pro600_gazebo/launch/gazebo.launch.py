from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory

import os


def generate_launch_description():
    description_share = get_package_share_directory('mycobot_pro600_description')
    gazebo_share = get_package_share_directory('mycobot_pro600_gazebo')
    ros_gz_sim_share = get_package_share_directory('ros_gz_sim')

    default_model = os.path.join(description_share, 'urdf', 'pro600_official_assets.urdf.xacro')
    default_world = os.path.join(gazebo_share, 'worlds', 'empty.world')

    use_rviz = LaunchConfiguration('use_rviz')
    world = LaunchConfiguration('world')
    model = LaunchConfiguration('model')

    # Jazzy 默认使用 Gazebo Sim / ros_gz，先加载可视化模型，不绑定 classic gazebo_ros2_control。
    robot_description = ParameterValue(
        Command(['xacro', ' ', model, ' ', 'use_ros2_control:=false']),
        value_type=str,
    )

    rsp_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[{'robot_description': robot_description}],
    )

    gz_sim_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(ros_gz_sim_share, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={'gz_args': ['-r ', world]}.items(),
    )

    spawn_entity = Node(
        package='ros_gz_sim',
        executable='create',
        output='screen',
        arguments=[
            '-topic',
            'robot_description',
            '-name',
            'mycobot_pro600',
            '-allow_renaming',
            'true',
            '-x',
            '0.0',
            '-y',
            '0.0',
            '-z',
            '0.05',
        ],
    )

    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        output='screen',
        arguments=['-d', os.path.join(description_share, 'rviz', 'pro600.rviz')],
        condition=IfCondition(use_rviz),
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'model',
            default_value=default_model,
            description='Gazebo 中加载的 xacro/urdf 路径。',
        ),
        DeclareLaunchArgument(
            'world',
            default_value=default_world,
            description='Gazebo Sim world 文件路径。',
        ),
        DeclareLaunchArgument(
            'use_rviz',
            default_value='true',
            description='是否同时启动 RViz2。',
        ),
        rsp_node,
        gz_sim_launch,
        spawn_entity,
        rviz_node,
    ])
