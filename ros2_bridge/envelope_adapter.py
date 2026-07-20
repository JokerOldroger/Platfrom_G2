def build_progress_envelope(*, route_name, device, correlation, percent, stage):
    return {
        'schema_version': 1,
        'interface_type': 'action',
        'message_type': 'progress',
        'route_name': route_name,
        'status': 'running',
        'device': device,
        'correlation': correlation,
        'progress': {
            'percent': percent,
            'stage': stage,
        },
    }


def build_result_envelope(*, route_name, device, correlation, final_pose):
    return {
        'schema_version': 1,
        'interface_type': 'action',
        'message_type': 'result',
        'route_name': route_name,
        'status': 'succeeded',
        'device': device,
        'correlation': correlation,
        'result': {
            'final_pose': final_pose,
        },
    }


def build_error_envelope(*, route_name, device, correlation, code, message):
    return {
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
        },
    }
