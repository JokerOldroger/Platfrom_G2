import requests
from django.conf import settings


def _bridge_base_url():
    return getattr(settings, 'ROS2_BRIDGE_BASE_URL', 'http://127.0.0.1:9001')


def _bridge_timeout_sec():
    return float(getattr(settings, 'ROS2_BRIDGE_TIMEOUT_SEC', 5))


def dispatch_ros2_bridge_command(*, route_name, interface_type, payload, device=None, correlation=None):
    """向 ROS2 Bridge 发送 dispatch 请求。

    第一阶段仅对 action 做最小闭环；topic/service 预留统一入口。
    """
    endpoint = f"{_bridge_base_url().rstrip('/')}/dispatch/{interface_type}"
    body = {
        'schema_version': 1,
        'transport': 'ros2',
        'interface_type': interface_type,
        'route_name': route_name,
        'device': device or {},
        'correlation': correlation or {},
        'body': payload,
    }
    response = requests.post(endpoint, json=body, timeout=_bridge_timeout_sec())
    response.raise_for_status()
    return response.json() if response.content else {'accepted': True}
