#!/usr/bin/env python3
"""将官方 mycobot_ros/noetic 的 Pro600 资产同步到当前 ROS2 包。

用途：
1. 保留当前仓库里的 ROS2 launch / controller / plugin 配置。
2. 复用官方 ROS1 包中的 urdf / xacro / meshes / moveit config 作为参考资产。
3. 不直接覆盖当前 ROS2 骨架，避免一次导入把结构打乱。
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from convert_collada_for_gazebo import convert_directory


def _copy_tree(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description='导入 mycobot_ros noetic 的 Pro600 官方资产。')
    parser.add_argument(
        '--ros1-root',
        required=True,
        help='本地 mycobot_ros/noetic 工作树路径，或其 mycobot_pro 目录路径。',
    )
    parser.add_argument(
        '--skip-gazebo-conversion',
        action='store_true',
        help='只导入官方资产，不生成 Gazebo Ogre2 兼容 STL。',
    )
    args = parser.parse_args()

    ros1_root = Path(args.ros1_root).expanduser().resolve()
    if not ros1_root.exists():
        raise SystemExit(f'路径不存在: {ros1_root}')

    if (ros1_root / 'mycobot_600').exists():
        mycobot_pro_root = ros1_root
    elif (ros1_root / 'mycobot_pro' / 'mycobot_600').exists():
        mycobot_pro_root = ros1_root / 'mycobot_pro'
    else:
        raise SystemExit(
            '未找到 mycobot_600 目录。请将 --ros1-root 指向 mycobot_ros/noetic 根目录，'
            '或其 mycobot_pro 目录。'
        )

    description_package_root = Path(__file__).resolve().parents[1]
    gazebo_package_root = description_package_root.parent / 'mycobot_pro600_gazebo'

    vendor_description_root = description_package_root / 'vendor_ros1'
    vendor_gazebo_root = gazebo_package_root / 'vendor_ros1'
    vendor_description_root.mkdir(parents=True, exist_ok=True)
    vendor_gazebo_root.mkdir(parents=True, exist_ok=True)

    copied = {
        'description': {
            'urdf': _copy_tree(
                mycobot_pro_root / 'mycobot_600' / 'urdf',
                vendor_description_root / 'mycobot_600' / 'urdf',
            ),
            'meshes': _copy_tree(
                mycobot_pro_root / 'mycobot_600' / 'meshes',
                vendor_description_root / 'mycobot_600' / 'meshes',
            ),
            'scripts': _copy_tree(
                mycobot_pro_root / 'mycobot_600' / 'scripts',
                vendor_description_root / 'mycobot_600' / 'scripts',
            ),
            'mycobot_description_meshes': _copy_tree(
                mycobot_pro_root.parent / 'mycobot_description' / 'urdf' / 'mycobot_pro_600',
                vendor_description_root / 'mycobot_description' / 'urdf' / 'mycobot_pro_600',
            ),
        },
        'gazebo': {
            'config': _copy_tree(
                mycobot_pro_root / 'mycobot_600_moveit' / 'config',
                vendor_gazebo_root / 'mycobot_600_moveit' / 'config',
            ),
            'launch': _copy_tree(
                mycobot_pro_root / 'mycobot_600_moveit' / 'launch',
                vendor_gazebo_root / 'mycobot_600_moveit' / 'launch',
            ),
        },
    }

    conversion = None
    official_mesh_dir = (
        vendor_description_root / 'mycobot_description' / 'urdf' / 'mycobot_pro_600'
    )
    if copied['description']['mycobot_description_meshes'] and not args.skip_gazebo_conversion:
        conversion = convert_directory(
            official_mesh_dir,
            description_package_root / 'meshes' / 'gazebo',
        )

    manifest = {
        'ros1_root': str(ros1_root),
        'mycobot_pro_root': str(mycobot_pro_root),
        'copied': copied,
        'gazebo_mesh_conversion': conversion,
        'next_steps': [
            '若 copied.description.mycobot_description_meshes 为 false，请补拉官方 mycobot_description 目录，'
            '否则 Pro600 的 dae mesh 视觉模型无法显示。',
            '对照 vendor_ros1/mycobot_600_moveit/config 下的关节限制、初始姿态与控制器配置，'
            '合并到 mycobot_pro600_gazebo/config/controllers.yaml。',
            '使用 official_gazebo.launch.py 加载三角化 STL、官方关节链和 gz_ros2_control。',
        ],
    }

    manifest_path = vendor_description_root / 'import_manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')

    print('已完成官方 Pro600 资产导入。')
    print(f'资产清单: {manifest_path}')
    print('当前不会自动覆盖 ROS2 launch 和控制器配置，请按清单逐步替换。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
