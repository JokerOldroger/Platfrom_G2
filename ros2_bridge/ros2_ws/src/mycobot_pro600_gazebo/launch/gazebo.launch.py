from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, RegisterEventHandler
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory

import os


def generate_launch_description():
    description_share = get_package_share_directory('mycobot_pro600_description')
    gazebo_share = get_package_share_directory('mycobot_pro600_gazebo')
    gazebo_ros_share = get_package_share_directory('gazebo_ros')

    default_model = os.path.join(description_share, 'urdf', 'pro600_official_assets.urdf.xacro')
    default_world = os.path.join(gazebo_share, 'worlds', 'empty.world')
    controllers_file = os.path.join(gazebo_share, 'config', 'controllers.yaml')

    use_rviz = LaunchConfiguration('use_rviz')
    world = LaunchConfiguration('world')
    model = LaunchConfiguration('model')

    robot_description = ParameterValue(
        Command(['xacro', ' ', model, ' ', 'use_ros2_control:=true']),
        value_type=str,
    )

    rsp_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[{'robot_description': robot_description}],
    )

    gazebo_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(gazebo_ros_share, 'launch', 'gazebo.launch.py')
        ),
        launch_arguments={'world': world}.items(),
    )

    spawn_entity = Node(
        package='gazebo_ros',
        executable='spawn_entity.py',
        output='screen',
        arguments=['-topic', 'robot_description', '-entity', 'mycobot_pro600'],
    )

    joint_state_broadcaster = Node(
        package='controller_manager',
        executable='spawner',
        output='screen',
        arguments=[
            'joint_state_broadcaster',
            '--controller-manager',
            '/controller_manager',
            '--param-file',
            controllers_file,
        ],
    )

    arm_controller = Node(
        package='controller_manager',
        executable='spawner',
        output='screen',
        arguments=[
            'arm_controller',
            '--controller-manager',
            '/controller_manager',
            '--param-file',
            controllers_file,
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
            description='Gazebo world 文件路径。',
        ),
        DeclareLaunchArgument(
            'use_rviz',
            default_value='true',
            description='是否同时启动 RViz2。',
        ),
        rsp_node,
        gazebo_launch,
        spawn_entity,
        RegisterEventHandler(
            OnProcessExit(
                target_action=spawn_entity,
                on_exit=[joint_state_broadcaster, arm_controller, rviz_node],
            )
        ),
    ])
