"""
Minimal arm01 ROS2 action server demo for fixed-waypoint execution.

This file is intentionally self-contained so the project can validate the
Bridge -> arm01 control flow before converting the repository into a full ROS2
package layout.
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from peripherals.robo_arm_driver import RoboArmControl
from peripherals.robo_arm_config import WAYPOINTS

try:
    import rclpy
    from rclpy.action import ActionServer
    from rclpy.node import Node
except ImportError:  # pragma: no cover - depends on ROS2 runtime
    rclpy = None
    ActionServer = None
    Node = object

try:
    from platfrom_g2_interfaces.action import ExecuteWaypointTrajectory
except ImportError:  # pragma: no cover - depends on generated ROS2 interfaces
    ExecuteWaypointTrajectory = None


class Arm01WaypointServer(Node):
    """Example action server that wraps the existing ElephantRobot driver."""

    def __init__(self):
        if rclpy is None:
            raise RuntimeError('rclpy is not available. Source ROS2 before running this demo.')
        if ExecuteWaypointTrajectory is None:
            raise RuntimeError(
                'ROS2 action interface ExecuteWaypointTrajectory is missing. '
                'Create the .action definition and build the interfaces package first.'
            )
        super().__init__('arm01')
        self._control = RoboArmControl()
        self._server = ActionServer(
            self,
            ExecuteWaypointTrajectory,
            'arm01/execute_waypoint_trajectory',
            execute_callback=self.execute_callback,
        )

    def destroy_node(self):
        if self._server is not None:
            self._server.destroy()
        if self._control is not None:
            self._control.end()
        return super().destroy_node()

    def execute_callback(self, goal_handle):
        trajectory = list(goal_handle.request.trajectory or [])
        speed = int(getattr(goal_handle.request, 'speed', 1000) or 1000)
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


def main():
    if rclpy is None:
        raise RuntimeError('rclpy is not available. Source ROS2 before running this demo.')
    rclpy.init(args=None)
    node = Arm01WaypointServer()
    try:
        node.get_logger().info('arm01 waypoint action server started.')
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
