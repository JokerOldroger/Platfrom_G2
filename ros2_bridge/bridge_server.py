import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from ros2_runtime import Ros2BridgeRuntimeUnavailable, Ros2RuntimeThread


_runtime_thread = None


def _runtime_enabled():
    return os.environ.get('ROS2_BRIDGE_USE_RUNTIME', '0') == '1'


def _get_runtime():
    global _runtime_thread
    if _runtime_thread is None:
        _runtime_thread = Ros2RuntimeThread()
    return _runtime_thread.get_runtime(timeout=5)


class BridgeRequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=200):
        encoded = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path == '/healthz':
            runtime_mode = 'rclpy' if _runtime_enabled() else 'mock'
            self._send_json({
                'status': 'ok',
                'bridge': 'ros2_bridge',
                'routes': ['arm.execute_trajectory', 'gripper.set_force'],
                'mode': runtime_mode,
            })
            return
        self._send_json({'detail': 'Not found.'}, status=404)

    def do_POST(self):
        if self.path != '/dispatch/action':
            self._send_json({'detail': 'Not found.'}, status=404)
            return

        content_length = int(self.headers.get('Content-Length', '0'))
        body = self.rfile.read(content_length).decode('utf-8') if content_length else '{}'
        payload = json.loads(body)

        if _runtime_enabled():
            try:
                runtime = _get_runtime()
                response = runtime.dispatch_action(
                    route_name=payload.get('route_name'),
                    device=payload.get('device') or {},
                    body=payload.get('body') or {},
                    correlation=payload.get('correlation') or {},
                )
                self._send_json(response, status=200)
                return
            except Ros2BridgeRuntimeUnavailable as exc:
                self._send_json({'accepted': False, 'detail': str(exc)}, status=503)
                return
            except Exception as exc:
                self._send_json({'accepted': False, 'detail': str(exc)}, status=500)
                return

        response = {
            'accepted': True,
            'bridge_request_id': f"mock_{payload.get('correlation', {}).get('outbox_id', 'unknown')}",
            'detail': 'Mock ROS2 bridge accepted the action.',
        }
        self._send_json(response, status=200)


def serve(host='127.0.0.1', port=9001):
    server = HTTPServer((host, port), BridgeRequestHandler)
    print(f'[ROS2 Bridge] Listening on http://{host}:{port}')
    server.serve_forever()
