import threading
from concurrent.futures import Future
from pathlib import Path

import yaml

try:
    import rclpy
    from rclpy.action import ActionClient
    from rclpy.node import Node
except ImportError:  # pragma: no cover - depends on ROS2 runtime
    rclpy = None
    ActionClient = None
    Node = object


class Ros2BridgeRuntimeUnavailable(RuntimeError):
    pass


class Ros2BridgeRuntime(Node):
    """Minimal ROS2 runtime for Django -> Bridge -> ROS2 dispatch."""

    def __init__(self, routes_path=None):
        if rclpy is None:
            raise Ros2BridgeRuntimeUnavailable(
                'rclpy is not available. Install ROS2 Python runtime before enabling live bridge dispatch.'
            )
        super().__init__('platfrom_g2_bridge')
        self._routes = self._load_routes(routes_path)
        self._action_clients = {}

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
        return {
            'accepted': True,
            'bridge_request_id': self._bridge_request_id(correlation),
            'detail': 'ROS2 runtime stub accepted arm trajectory action.',
            'runtime': 'rclpy',
            'route_name': action_name,
            'node': route.get('node') or device.get('id') or 'arm01',
            'goal_preview': {
                'trajectory': goal.get('trajectory') or [],
                'pose': goal.get('pose'),
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
