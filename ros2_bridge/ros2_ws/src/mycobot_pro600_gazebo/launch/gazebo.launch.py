from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    RegisterEventHandler,
    SetEnvironmentVariable,
)
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, EnvironmentVariable, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory

import os


def generate_launch_description():
    description_share = get_package_share_directory('mycobot_pro600_description')
    gazebo_share = get_package_share_directory('mycobot_pro600_gazebo')
    ros_gz_sim_share = get_package_share_directory('ros_gz_sim')

    default_model = os.path.join(description_share, 'urdf', 'pro600_description.urdf.xacro')
    default_world = os.path.join(gazebo_share, 'worlds', 'empty.world')
    default_controllers_file = os.path.join(gazebo_share, 'config', 'controllers.yaml')
    package_share_root = os.path.dirname(description_share)

    use_rviz = LaunchConfiguration('use_rviz')
    world = LaunchConfiguration('world')
    model = LaunchConfiguration('model')
    controllers_file = LaunchConfiguration('controllers_file')
    use_gazebo_meshes = LaunchConfiguration('use_gazebo_meshes')

    # 控制器配置以绝对路径传给 Gazebo 插件，避免安装空间和源码空间解析不一致。
    robot_description = ParameterValue(
        Command([
            'xacro',
            ' ',
            model,
            ' ',
            'use_ros2_control:=true',
            ' ',
            'controllers_file:=',
            controllers_file,
            ' ',
            'use_gazebo_meshes:=',
            use_gazebo_meshes,
        ]),
        value_type=str,
    )

    rsp_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description,
            'use_sim_time': True,
        }],
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

    joint_state_broadcaster_spawner = Node(
        package='controller_manager',
        executable='spawner',
        output='screen',
        arguments=[
            'joint_state_broadcaster',
            '--controller-manager',
            '/controller_manager',
            '--controller-manager-timeout',
            '60',
        ],
    )

    arm_controller_spawner = Node(
        package='controller_manager',
        executable='spawner',
        output='screen',
        arguments=[
            'arm_controller',
            '--controller-manager',
            '/controller_manager',
            '--controller-manager-timeout',
            '60',
        ],
    )

    start_controllers_after_spawn = RegisterEventHandler(
        OnProcessExit(
            target_action=spawn_entity,
            on_exit=[
                joint_state_broadcaster_spawner,
                arm_controller_spawner,
            ],
        )
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
            'controllers_file',
            default_value=default_controllers_file,
            description='与所选模型关节名称匹配的 ros2_control 配置。',
        ),
        DeclareLaunchArgument(
            'use_rviz',
            default_value='true',
            description='是否同时启动 RViz2。',
        ),
        DeclareLaunchArgument(
            'use_gazebo_meshes',
            default_value='false',
            description='官方模型是否使用转换后的 Gazebo STL 网格。',
        ),
        SetEnvironmentVariable(
            name='GZ_SIM_RESOURCE_PATH',
            value=[
                package_share_root,
                ':',
                EnvironmentVariable('GZ_SIM_RESOURCE_PATH', default_value=''),
            ],
        ),
        SetEnvironmentVariable(
            name='IGN_GAZEBO_RESOURCE_PATH',
            value=[
                package_share_root,
                ':',
                EnvironmentVariable('IGN_GAZEBO_RESOURCE_PATH', default_value=''),
            ],
        ),
        rsp_node,
        gz_sim_launch,
        # 先注册事件处理器，避免 create 进程快速退出时漏掉控制器启动事件。
        start_controllers_after_spawn,
        spawn_entity,
        rviz_node,
    ])
