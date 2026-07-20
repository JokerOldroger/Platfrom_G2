from django.conf import settings


def default_device_id():
    return getattr(settings, 'MQTT_DEFAULT_DEVICE_ID', 'esp32_1')


def default_control_topic():
    from ..mqtt import _device_control_topic

    return _device_control_topic(default_device_id())


def extract_device_id_from_topic(topic):
    from ..mqtt import _extract_device_id_from_topic

    return _extract_device_id_from_topic(topic)


def dispatch_transport_message(*, transport, topic, payload, interface_type, route_name, device=None, correlation=None):
    if transport == 'mqtt':
        from ..mqtt import publish_device_command

        publish_device_command(topic, payload)
        return {'accepted': True, 'transport': 'mqtt'}
    if transport == 'ros2':
        from ..ros2_bridge_client import dispatch_ros2_bridge_command

        return dispatch_ros2_bridge_command(
            route_name=route_name,
            interface_type=interface_type,
            payload=payload,
            device=device,
            correlation=correlation,
        )
    raise ValueError(f'Unsupported transport: {transport}')
