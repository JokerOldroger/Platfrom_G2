from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory

import os


def generate_launch_description():
    description_share = get_package_share_directory('mycobot_pro600_description')
    gazebo_share = get_package_share_directory('mycobot_pro600_gazebo')
    mesh_names = ('base', 'link1', 'link2', 'link3', 'link4', 'link5', 'link6')
    missing_meshes = [
        name
        for name in mesh_names
        if not os.path.exists(
            os.path.join(description_share, 'meshes', 'gazebo', f'{name}.stl')
        )
    ]
    if missing_meshes:
        raise RuntimeError(
            f'缺少转换后的 Pro600 Gazebo 网格: {missing_meshes}。'
            '请在 description 包源码目录运行 '
            '`python3 scripts/convert_collada_for_gazebo.py`，然后重新 colcon build。'
        )

    return LaunchDescription([
        DeclareLaunchArgument('use_rviz', default_value='false'),
        DeclareLaunchArgument(
            'world',
            default_value=os.path.join(gazebo_share, 'worlds', 'empty.world'),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(gazebo_share, 'launch', 'gazebo.launch.py')
            ),
            launch_arguments={
                'model': os.path.join(
                    description_share,
                    'urdf',
                    'pro600_official_assets.urdf.xacro',
                ),
                'controllers_file': os.path.join(
                    gazebo_share,
                    'config',
                    'controllers_official.yaml',
                ),
                'use_gazebo_meshes': 'true',
                'use_rviz': LaunchConfiguration('use_rviz'),
                'world': LaunchConfiguration('world'),
            }.items(),
        ),
    ])
