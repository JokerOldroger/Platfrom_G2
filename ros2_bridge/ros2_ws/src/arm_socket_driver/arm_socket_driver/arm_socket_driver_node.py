import sys
import time
from pathlib import Path

import rclpy
from rclpy.action import ActionServer
from rclpy.node import Node


def _inject_project_root():
    """允许节点直接复用当前仓库里的现有 socket 封装。"""
    current = Path(__file__).resolve()
    for parent in current.parents:
        peripherals_dir = parent / 'peripherals'
        if (peripherals_dir / 'robo_arm_driver.py').exists():
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            if str(peripherals_dir) not in sys.path:
                sys.path.insert(0, str(peripherals_dir))
            return parent
    raise RuntimeError(
        'Cannot locate project root containing peripherals/robo_arm_driver.py. '
        'Deploy this package inside the Platform_G2 repository or adjust sys.path.'
    )


PROJECT_ROOT = _inject_project_root()

from peripherals.robo_arm_driver import RoboArmControl  # noqa: E402
from peripherals.robo_arm_config import WAYPOINTS  # noqa: E402
from platfrom_g2_interfaces.action import ExecuteWaypointTrajectory  # noqa: E402


class ArmSocketDriverNode(Node):
    """将 ElephantRobot socket API 包装成 ROS2 ActionServer。"""

    def __init__(self):
        super().__init__('arm01')
        self._control = RoboArmControl()
        self._server = ActionServer(
            self,
            ExecuteWaypointTrajectory,
            'arm01/execute_waypoint_trajectory',
            execute_callback=self.execute_callback,
        )
        self.get_logger().info(
            'arm01 action server started. '
            f'Using Pro600 socket backend from {PROJECT_ROOT / "peripherals" / "robo_arm_driver.py"}'
        )

    def destroy_node(self):
        if self._server is not None:
            self._server.destroy()
        if self._control is not None:
            self._control.end()
        return super().destroy_node()

    def execute_callback(self, goal_handle):
        trajectory = list(goal_handle.request.trajectory or [])
        speed = int(goal_handle.request.speed or 1000)
        result = ExecuteWaypointTrajectory.Result()

        if not trajectory:
            result.success = False
            result.message = 'Empty trajectory.'
            goal_handle.abort()
            return result

        for index, waypoint_name in enumerate(trajectory, start=1):
            if waypoint_name not in WAYPOINTS:
                result.success = False
                result.message = f'Unknown waypoint: {waypoint_name}'
                result.final_waypoint = waypoint_name
                goal_handle.abort()
                return result

            self.get_logger().info(f'Executing waypoint {waypoint_name} at speed {speed}')
            execution_result = self._control.to_waypoint(waypoint_name, speed=speed)

            feedback = ExecuteWaypointTrajectory.Feedback()
            feedback.percent = float(index) / float(len(trajectory)) * 100.0
            feedback.stage = waypoint_name
            goal_handle.publish_feedback(feedback)

            if execution_result != 'Success':
                result.success = False
                result.message = f'Waypoint execution failed at {waypoint_name}'
                result.final_waypoint = waypoint_name
                goal_handle.abort()
                return result

            time.sleep(0.2)

        result.success = True
        result.message = 'Trajectory completed.'
        result.final_waypoint = trajectory[-1]
        goal_handle.succeed()
        return result


def main(args=None):
    rclpy.init(args=args)
    node = ArmSocketDriverNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
