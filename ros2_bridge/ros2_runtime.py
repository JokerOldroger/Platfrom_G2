import threading
from concurrent.futures import Future
import os
from pathlib import Path

import requests
import yaml

try:
    import rclpy
    from rclpy.action import ActionClient
    from rclpy.node import Node
    from action_msgs.msg import GoalStatus
    from platfrom_g2_interfaces.action import ExecuteWaypointTrajectory
except ImportError:  # pragma: no cover - depends on ROS2 runtime
    rclpy = None
    ActionClient = None
    GoalStatus = None
    ExecuteWaypointTrajectory = None
    Node = object


class Ros2BridgeRuntimeUnavailable(RuntimeError):
    pass


class Ros2BridgeRuntime(Node):
    """Minimal ROS2 runtime for Django -> Bridge -> ROS2 dispatch."""

    def __init__(self, routes_path=None):
        if rclpy is None or ExecuteWaypointTrajectory is None:
            raise Ros2BridgeRuntimeUnavailable(
                'rclpy or platfrom_g2_interfaces is not available. '
                'Source the ROS2 workspace before enabling live bridge dispatch.'
            )
        super().__init__('platfrom_g2_bridge')
        self._routes = self._load_routes(routes_path)
        self._action_clients = {}
        self._reply_url = os.environ.get(
            'ROS2_BRIDGE_REPLY_URL',
            'http://127.0.0.1:8000/api/v1/internal/bridge/replies/',
        )

    def dispatch_action(self, *, route_name, device, body, correlation):
        route = self._routes.get(route_name)
        if not route:
            raise ValueError(f'Unknown ROS2 route: {route_name}')
        if route.get('interface_type') != 'action':
            raise ValueError(f'Route {route_name} is not configured as an action.')

        if route_name == 'arm.execute_trajectory':
            return self._dispatch_arm_execute_trajectory(
                route=route,
                device=device or {},
                body=body or {},
                correlation=correlation or {},
            )
        if route_name == 'gripper.set_force':
            return self._dispatch_gripper_set_force(
                route=route,
                device=device or {},
                body=body or {},
                correlation=correlation or {},
            )
        raise ValueError(f'ROS2 action route not implemented yet: {route_name}')

    def _dispatch_arm_execute_trajectory(self, *, route, device, body, correlation):
        action_name = body.get('action_name') or 'arm.execute_trajectory'
        goal = body.get('goal') or {}
        trajectory = goal.get('trajectory') or body.get('trajectory') or []
        speed = int(goal.get('speed') or body.get('speed') or 300)
        request_id = str(goal.get('request_id') or body.get('request_id') or self._bridge_request_id(correlation))
        action_topic = route.get('action_topic') or f"/{route.get('node') or device.get('id') or 'arm01'}/execute_waypoint_trajectory"

        if not trajectory:
            raise ValueError('arm.execute_trajectory goal requires trajectory.')

        client = self._get_action_client(
            action_topic,
            ExecuteWaypointTrajectory,
        )
        if not client.wait_for_server(timeout_sec=float(route.get('server_timeout_sec', 5.0))):
            raise Ros2BridgeRuntimeUnavailable(f'ROS2 action server is not available: {action_topic}')

        goal_msg = ExecuteWaypointTrajectory.Goal()
        goal_msg.trajectory = [str(item) for item in trajectory]
        goal_msg.speed = speed
        goal_msg.request_id = request_id

        send_future = client.send_goal_async(
            goal_msg,
            feedback_callback=lambda feedback_msg: self._post_feedback(
                route_name=action_name,
                device=self._normalize_device(route, device),
                correlation=correlation,
                feedback=feedback_msg.feedback,
            ),
        )
        send_future.add_done_callback(
            lambda future: self._handle_goal_response(
                future,
                route_name=action_name,
                device=self._normalize_device(route, device),
                correlation=correlation,
            )
        )

        return {
            'accepted': True,
            'bridge_request_id': self._bridge_request_id(correlation),
            'detail': 'ROS2 action goal sent to arm action server.',
            'runtime': 'rclpy',
            'route_name': action_name,
            'node': route.get('node') or device.get('id') or 'arm01',
            'action_topic': action_topic,
            'goal_preview': {
                'trajectory': trajectory,
                'speed': speed,
                'request_id': request_id,
            },
        }

    def _dispatch_gripper_set_force(self, *, route, device, body, correlation):
        goal = body.get('goal') or {}
        return {
            'accepted': True,
            'bridge_request_id': self._bridge_request_id(correlation),
            'detail': 'ROS2 runtime stub accepted gripper force action.',
            'runtime': 'rclpy',
            'route_name': body.get('action_name') or 'gripper.set_force',
            'node': route.get('node') or device.get('id') or 'gripper01',
            'goal_preview': {
                'mode': goal.get('mode'),
                'target_force': goal.get('target_force'),
            },
        }

    def _bridge_request_id(self, correlation):
        outbox_id = correlation.get('outbox_id', 'unknown')
        return f'ros2_{outbox_id}'

    def _get_action_client(self, action_topic, action_type):
        if action_topic not in self._action_clients:
            self._action_clients[action_topic] = ActionClient(self, action_type, action_topic)
        return self._action_clients[action_topic]

    def _normalize_device(self, route, device):
        if device:
            return device
        return {
            'type': route.get('device_type') or 'roboarm',
            'id': route.get('node') or 'arm01',
        }

    def _post_bridge_reply(self, payload):
        try:
            response = requests.post(self._reply_url, json=payload, timeout=3)
            response.raise_for_status()
        except Exception as exc:  # pragma: no cover - depends on Django runtime
            self.get_logger().error(f'Failed to post bridge reply to Django: {exc!r}')

    def _post_feedback(self, *, route_name, device, correlation, feedback):
        self._post_bridge_reply({
            'schema_version': 1,
            'interface_type': 'action',
            'message_type': 'progress',
            'route_name': route_name,
            'status': 'running',
            'device': device,
            'correlation': correlation,
            'progress': {
                'percent': float(feedback.percent),
                'stage': feedback.stage,
            },
        })

    def _handle_goal_response(self, future, *, route_name, device, correlation):
        try:
            goal_handle = future.result()
        except Exception as exc:
            self._post_action_error(
                route_name=route_name,
                device=device,
                correlation=correlation,
                code='goal_send_failed',
                message=str(exc),
            )
            return

        if not goal_handle.accepted:
            self._post_action_error(
                route_name=route_name,
                device=device,
                correlation=correlation,
                code='goal_rejected',
                message='ROS2 action server rejected the goal.',
            )
            return

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            lambda done_future: self._handle_action_result(
                done_future,
                route_name=route_name,
                device=device,
                correlation=correlation,
            )
        )

    def _handle_action_result(self, future, *, route_name, device, correlation):
        try:
            wrapped_result = future.result()
            status_code = wrapped_result.status
            result = wrapped_result.result
        except Exception as exc:
            self._post_action_error(
                route_name=route_name,
                device=device,
                correlation=correlation,
                code='result_failed',
                message=str(exc),
            )
            return

        if status_code == GoalStatus.STATUS_SUCCEEDED and result.success:
            self._post_bridge_reply({
                'schema_version': 1,
                'interface_type': 'action',
                'message_type': 'result',
                'route_name': route_name,
                'status': 'succeeded',
                'device': device,
                'correlation': correlation,
                'result': {
                    'message': result.message,
                    'final_pose': result.final_waypoint,
                    'final_waypoint': result.final_waypoint,
                },
            })
            return

        self._post_action_error(
            route_name=route_name,
            device=device,
            correlation=correlation,
            code='action_failed',
            message=result.message or f'ROS2 action finished with status code {status_code}.',
            extra={'final_waypoint': result.final_waypoint, 'status_code': status_code},
        )

    def _post_action_error(self, *, route_name, device, correlation, code, message, extra=None):
        self._post_bridge_reply({
            'schema_version': 1,
            'interface_type': 'action',
            'message_type': 'error',
            'route_name': route_name,
            'status': 'failed',
            'device': device,
            'correlation': correlation,
            'error': {
                'code': code,
                'message': message,
                **(extra or {}),
            },
        })

    @staticmethod
    def _load_routes(routes_path=None):
        path = Path(routes_path or Path(__file__).with_name('routes.yaml'))
        with path.open('r', encoding='utf-8') as fh:
            data = yaml.safe_load(fh) or {}
        return data.get('routes', {})


class Ros2RuntimeThread:
    """Keeps a ROS2 node alive in a background executor thread."""

    def __init__(self, routes_path=None):
        self._routes_path = routes_path
        self._thread = None
        self._runtime = None
        self._ready = Future()

    def start(self):
        if self._thread is not None:
            return

        def runner():
            try:
                rclpy.init(args=None)
                runtime = Ros2BridgeRuntime(routes_path=self._routes_path)
                self._runtime = runtime
                self._ready.set_result(runtime)
                rclpy.spin(runtime)
            except Exception as exc:  # pragma: no cover - runtime failure path
                if not self._ready.done():
                    self._ready.set_exception(exc)
            finally:
                if self._runtime is not None:
                    self._runtime.destroy_node()
                if rclpy is not None and rclpy.ok():
                    rclpy.shutdown()

        self._thread = threading.Thread(target=runner, daemon=True)
        self._thread.start()

    def get_runtime(self, timeout=5):
        self.start()
        return self._ready.result(timeout=timeout)
