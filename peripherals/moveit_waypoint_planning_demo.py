"""
MoveIt 第二阶段路径规划示例

用途：
1. 使用与固定点位测试相同的 waypoint 名称，构建 MoveIt named-target / joint-goal 调试入口。
2. 为后续 ROS2 Bridge 中的 MOVE_ARM action 提供规划层参考实现。

说明：
1. 本脚本以 ROS2 + MoveIt2 Python 环境为前提。
2. 若当前环境未安装 moveit_py，本脚本会给出提示并退出。
3. 第一阶段仍建议使用 fixed_waypoint_arm_test.py 直接调 ElephantRobot，
   第二阶段再切换到本脚本验证规划链路。
"""

from robo_arm_config import WAYPOINTS


def _try_import_moveit():
    try:
        from moveit.planning import MoveItPy
        from moveit.core.robot_state import RobotState
        return MoveItPy, RobotState
    except ImportError:
        return None, None


def build_joint_goal(waypoint_name):
    if waypoint_name not in WAYPOINTS:
        raise ValueError(f'Unknown waypoint: {waypoint_name}')
    return WAYPOINTS[waypoint_name]


def demo_plan_named_waypoints():
    MoveItPy, RobotState = _try_import_moveit()
    if MoveItPy is None:
        print('[MoveIt Demo] moveit_py is not available in the current environment.')
        print('[MoveIt Demo] Install ROS2 + MoveIt2 Python bindings before stage-2 debugging.')
        return

    moveit_py = MoveItPy(node_name='platfrom_g2_moveit_demo')
    planning_component = moveit_py.get_planning_component('arm')
    robot_model = moveit_py.get_robot_model()

    sequence = ['home', 'powder_station_above', 'powder_pick', 'powder_place']

    for waypoint_name in sequence:
        joint_goal = build_joint_goal(waypoint_name)
        print(f'[MoveIt Demo] Planning to {waypoint_name}: {joint_goal}')

        robot_state = RobotState(robot_model)
        robot_state.set_to_default_values()
        robot_state.set_joint_group_positions('arm', joint_goal)

        planning_component.set_goal_state(robot_state=robot_state)
        plan_result = planning_component.plan()

        if not plan_result:
            print(f'[MoveIt Demo] Planning failed for waypoint: {waypoint_name}')
            continue

        print(f'[MoveIt Demo] Planning succeeded for waypoint: {waypoint_name}')
        # 第二阶段真机联调时可放开执行：
        # moveit_py.execute(plan_result.trajectory, controllers=[])


if __name__ == '__main__':
    demo_plan_named_waypoints()
