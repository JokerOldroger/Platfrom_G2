"""
固定点位机械臂运动测试

用途：
1. 复用前期采集的关节角固定点位，验证机械臂能否稳定到达目标位。
2. 为后续 Django -> ROS2 Bridge -> MOVE_ARM action 第一阶段闭环提供最小执行基线。

运行示例：
    python fixed_waypoint_arm_test.py
"""

from robo_arm_driver import RoboArmControl
from robo_arm_config import WAYPOINTS


TEST_SEQUENCES = {
    'reactor_cycle': ['home', 'safe_a', 'reactor_hover', 'safe_a', 'home'],
    'powder_cycle': ['home', 'powder_station_above', 'powder_pick', 'powder_place', 'home'],
}


def print_waypoints():
    print('Available waypoints:')
    for name, joints in WAYPOINTS.items():
        print(f'  - {name}: {joints}')


def run_sequence(control, sequence_name, speed=1000):
    waypoint_names = TEST_SEQUENCES[sequence_name]
    print(f'[Test] Running sequence: {sequence_name}')
    result = control.run_waypoint_sequence(waypoint_names, speed=speed)
    print(f'[Test] Sequence result: {result}')
    return result


def main():
    print_waypoints()
    control = RoboArmControl()
    try:
        for sequence_name in ('reactor_cycle', 'powder_cycle'):
            run_sequence(control, sequence_name, speed=1000)
    finally:
        control.end()


if __name__ == '__main__':
    main()
