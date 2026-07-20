# 注意到如果我们直接使用通常的python manage.py runserver 0.0.0.0:8000会造成创建了两个MQTT Client
# 这是因为Django会创建两个线程，其中一个是主线程，另外一个是支线程用来在必要的时候刷新你的主线程
# 所以说我们可以在开启server的时候直接将支线程ban掉，即使用 --noreload指示
# 当然这么做我也不知道会不会对其他的东西产生影响，所以说我们可以通过以下Stack Overflow的回答来规避
# https://stackoverflow.com/questions/33814615/how-to-avoid-appconfig-ready-method-running-twice-in-django
# 依照上面给出的回答我们添加 if os.environ.get('RUN_MAIN') 判断即可规避掉在支线程当中的任何操作
# MQTT后端当中显示的连接数也变成2

import paho.mqtt.client as mqtt
from django.conf import settings
import os
import socket
import sys
import json
import threading
import time
from datetime import datetime, timedelta
from django.utils import timezone

from django.apps import apps
from django.db import models

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .models import Motor, MotorEvent, MotorData, BatchJob, BatchStepExecution, CommandOutbox, TelemetryIngest, Spinning
from .orchestration.dispatch_runtime import (
    default_device_id as orchestration_default_device_id,
    dispatch_transport_message as orchestration_dispatch_transport_message,
    extract_device_id_from_topic as orchestration_extract_device_id_from_topic,
)
from .orchestration.step_executors import default_step_executor_registry
from .orchestration.service import dispatch_ready_steps, handle_device_reply

ongoing_events = []
client = None

# 设备状态内存缓存（用于实时追踪与 WebSocket 广播）
# 结构：{device_id: {'last_heartbeat': datetime, 'is_online': bool, 'task_status': str, 'telemetry': dict}}
_device_states = {}
_device_states_lock = threading.Lock()

# 后端 MQTT 客户端与 Broker 的连接状态
_mqtt_connection_state = {'connected': False, 'since': None, 'reason': ''}
_mqtt_connection_lock = threading.Lock()

# 后端 MQTT 自动重连配置与状态
MQTT_AUTO_RECONNECT_MIN_DELAY = getattr(settings, 'MQTT_AUTO_RECONNECT_MIN_DELAY', 2)
MQTT_AUTO_RECONNECT_MAX_DELAY = getattr(settings, 'MQTT_AUTO_RECONNECT_MAX_DELAY', 90)
MQTT_AUTO_RECONNECT_MULTIPLIER = getattr(settings, 'MQTT_AUTO_RECONNECT_MULTIPLIER', 2)

_auto_reconnect_state = {
    'enabled': False,
    'attempts': 0,
    'next_attempt_at': None,
    'in_progress': False,
}
_auto_reconnect_lock = threading.Lock()

HEARTBEAT_TIMEOUT_SECONDS = 90  # 超过此时间未收到心跳则判定为离线

# 会阻塞新任务下发的设备状态
NON_DISPATCHABLE_STATUSES = ('busy', 'estopped', 'error', 'completed', 'offline')


def _get_channel_layer():
    return get_channel_layer()


def _broadcast(event_type, payload):
    """向 WebSocket 的 mqtt_group 广播标准化消息。"""
    channel_layer = _get_channel_layer()
    if channel_layer is None:
        return
    package = {
        'type': 'mqtt_msg_broadcast',
        'topic': event_type,
        'timestamp': timezone.now().isoformat(),
        **payload,
    }
    try:
        async_to_sync(channel_layer.group_send)('mqtt_group', package)
    except Exception as exc:
        print(f'WebSocket broadcast failed: {exc}')


def _set_mqtt_connection_state(connected, reason=''):
    """设置后端 MQTT 与 Broker 的连接状态，状态变化时向 WebSocket 广播。"""
    global _mqtt_connection_state
    with _mqtt_connection_lock:
        previous = _mqtt_connection_state.get('connected')
        if previous == connected:
            return
        now = timezone.now()
        _mqtt_connection_state = {
            'connected': connected,
            'since': now.isoformat(),
            'reason': reason,
        }
        print(f"MQTT connection state changed: connected={connected}, reason={reason}")

    if connected:
        _reset_auto_reconnect()
    elif _auto_reconnect_state['enabled']:
        # 状态由连通变为断开时，启动自动重连退避
        _schedule_next_auto_reconnect(reason=reason)

    _broadcast('mqtt_connection_status', {
        'connected': connected,
        'reason': reason,
        'since': _mqtt_connection_state['since'],
    })


def _reset_auto_reconnect():
    """重置自动重连退避计数器。"""
    with _auto_reconnect_lock:
        _auto_reconnect_state['attempts'] = 0
        _auto_reconnect_state['next_attempt_at'] = None
        _auto_reconnect_state['in_progress'] = False


def _schedule_next_auto_reconnect(reason=''):
    """安排下一次自动重连尝试，使用指数退避。"""
    with _auto_reconnect_lock:
        attempts = _auto_reconnect_state['attempts']
        delay = min(
            MQTT_AUTO_RECONNECT_MAX_DELAY,
            MQTT_AUTO_RECONNECT_MIN_DELAY * (MQTT_AUTO_RECONNECT_MULTIPLIER ** attempts)
        )
        _auto_reconnect_state['next_attempt_at'] = time.time() + delay
        _auto_reconnect_state['attempts'] = attempts + 1
    print(f"MQTT auto-reconnect scheduled in {delay}s (attempt {attempts + 1}), reason={reason}")


def _do_auto_reconnect():
    """执行一次自动重连尝试，失败则继续安排下一次。"""
    with _auto_reconnect_lock:
        if _auto_reconnect_state['in_progress']:
            return
        _auto_reconnect_state['in_progress'] = True

    try:
        print('MQTT auto-reconnect attempting...')
        result = _perform_reconnect()
        if result.get('connected'):
            print('MQTT auto-reconnect succeeded')
            _reset_auto_reconnect()
        else:
            _schedule_next_auto_reconnect(reason='auto_reconnect_attempt_failed')
    except Exception as exc:
        print(f'MQTT auto-reconnect attempt failed: {exc}')
        _schedule_next_auto_reconnect(reason=f'auto_reconnect_exception_{exc}')
    finally:
        with _auto_reconnect_lock:
            _auto_reconnect_state['in_progress'] = False


def get_mqtt_connection_state():
    """返回后端 MQTT 与 Broker 的连接状态副本。"""
    with _mqtt_connection_lock:
        return dict(_mqtt_connection_state)


def _extract_device_id_from_topic(topic):
    """从 Topic 名提取 device_id。

    支持两种层级：
      - 新层级: esp32/<mac>/heartbeat -> esp32_<mac>
      - 旧层级: esp32_1/heartbeat     -> esp32_1 (兼容旧设备)
    """
    if not topic:
        return None
    parts = topic.split('/')
    # 新层级：esp32/<mac_suffix>/<type>
    if len(parts) >= 2 and parts[0] == 'esp32' and len(parts[1]) == 12:
        return f"esp32_{parts[1]}"
    # 兼容旧层级：esp32_1/<type>
    if parts and parts[0].startswith('esp32_'):
        return parts[0]
    return None


def _device_id_to_mac(device_id):
    """根据 device_id（如 esp32_7cdfa1e6d3cc）反推出 MAC 地址（带冒号）。"""
    if device_id and device_id.startswith('esp32_') and len(device_id) == 6 + 12:
        hex_mac = device_id[6:]
        return ':'.join(hex_mac[i:i + 2] for i in range(0, 12, 2))
    return ''


def _device_control_topic(device_id):
    """根据 device_id 生成对应的 MQTT 控制 topic。"""
    if not device_id:
        return None
    if device_id.startswith('esp32_') and len(device_id) == 6 + 12:
        return f"esp32/{device_id[6:]}/control"
    # 兼容旧 topic
    return f"{device_id}/control"


def _ensure_device_state(device_id):
    """确保 device_id 在内存状态表中有条目；若数据库中不存在则自动创建（便于后续注册表管理）。"""
    if not device_id:
        return None
    with _device_states_lock:
        if device_id not in _device_states:
            _device_states[device_id] = {
                'last_heartbeat': None,
                'is_online': False,
                'task_status': 'idle',
                'current_task': {},
                'active_motors': set(),
                'telemetry': {},
                'client_id': '',
            }
            # 尝试在数据库中创建或获取 Device 记录
            try:
                Device = apps.get_model('main_page', 'Device')
                Device.objects.get_or_create(
                    device_id=device_id,
                    defaults={
                        'label': device_id,
                        'is_registered': True,
                        'mac_address': _device_id_to_mac(device_id),
                    }
                )
            except Exception as exc:
                print(f'Auto-create Device failed for {device_id}: {exc}')
        return _device_states[device_id]


def is_device_online(device_id):
    """判断指定 device_id 当前是否在线（基于内存实时状态）。"""
    state = _ensure_device_state(device_id)
    if state is None:
        return False
    return state.get('is_online', False)


def _auto_release_stale_busy_state(device_id, grace_seconds=5):
    """若设备长期处于 busy 且已远超预期完成时间，自动释放为 idle，避免状态死锁。"""
    state = _ensure_device_state(device_id)
    if state is None:
        return
    if state.get('task_status') != 'busy':
        return
    current_task = state.get('current_task') or {}
    expected_finished_at = current_task.get('expected_finished_at')
    if not expected_finished_at:
        return
    try:
        expected = datetime.fromisoformat(expected_finished_at)
    except Exception:
        return
    if timezone.now() > expected + timedelta(seconds=grace_seconds):
        print(f'Auto-release stale busy state for {device_id} (expected finished at {expected_finished_at})')
        running_motors = set(state.get('active_motors', set()))
        _set_device_task_status(device_id, 'idle', current_task={})
        state['active_motors'] = set()
        # 任务已超时但未收到 task_finished，清零所有电机的 RPM 与健康状态
        for motor_key in state.get('telemetry', {}):
            state['telemetry'][motor_key]['rpm'] = 0
            state['telemetry'][motor_key]['health_status'] = 'idle'
            state['telemetry'][motor_key]['zero_samples'] = 0
        try:
            Device = apps.get_model('main_page', 'Device')
            Device.objects.filter(device_id=device_id).update(
                telemetry=state['telemetry'],
                updated_at=timezone.now(),
            )
        except Exception as exc:
            print(f'Auto-release telemetry DB update failed: {exc}')
        # 同步将仍处于 SENT/RUNNING 的 Spinning 记录置为 FINISHED，避免 Registration List 卡死
        _finish_stale_spinning_records(device_id, running_motors, reason='auto_release')


def can_dispatch_to_device(device_id):
    """
    判断是否可以向指定 device_id 下发新任务（设备级）。
    返回 (ok, reason)。
    """
    state = _ensure_device_state(device_id)
    if state is None:
        return False, 'Unknown device'
    # 防御性清理：若 busy 状态已过期，先自动释放
    _auto_release_stale_busy_state(device_id)
    if not state.get('is_online', False):
        return False, 'Device is offline'
    task_status = state.get('task_status', 'idle')
    if task_status in NON_DISPATCHABLE_STATUSES:
        status_label = {
            'busy': 'Device is busy',
            'estopped': 'Device is in emergency stop state. Resume before dispatch.',
            'error': 'Device has an error. Acknowledge before dispatch.',
            'completed': 'Device has a completed task. Acknowledge before dispatch.',
            'offline': 'Device is offline',
        }
        return False, status_label.get(task_status, f'Device status is {task_status}')
    return True, ''


def can_dispatch_motor(device_id, motor_index):
    """
    判断是否可以向指定设备的指定电机下发新任务（电机级）。
    当设备处于 busy 状态时，只要目标电机本身不在 active_motors 中，仍然可下发。
    返回 (ok, reason)。
    """
    state = _ensure_device_state(device_id)
    if state is None:
        return False, 'Unknown device'
    _auto_release_stale_busy_state(device_id)
    if not state.get('is_online', False):
        return False, 'Device is offline'
    task_status = state.get('task_status', 'idle')
    if task_status in ('estopped', 'error', 'completed', 'offline'):
        status_label = {
            'estopped': 'Device is in emergency stop state. Resume before dispatch.',
            'error': 'Device has an error. Acknowledge before dispatch.',
            'completed': 'Device has a completed task. Acknowledge before dispatch.',
            'offline': 'Device is offline',
        }
        return False, status_label.get(task_status, f'Device status is {task_status}')
    if task_status == 'busy':
        active_motors = state.get('active_motors', set())
        if motor_index in active_motors:
            return False, f'Motor {motor_index} is busy'
    return True, ''


def resolve_dispatchable_device_id(preferred_device_id=None, motor_index=None):
    """
    解析当前可用于下发任务的设备 ID。
    优先使用 preferred_device_id；若 motor_index 提供，则按电机级可用性判断；
    否则按设备级可用性判断。若首选不可用，则遍历所有已注册设备寻找可用设备；
    若都没有，则回退到 settings.MQTT_DEFAULT_DEVICE_ID。
    """
    dispatch_check = can_dispatch_motor if motor_index is not None else can_dispatch_to_device

    if preferred_device_id:
        _auto_release_stale_busy_state(preferred_device_id)
        if motor_index is not None:
            ok, _ = can_dispatch_motor(preferred_device_id, motor_index)
        else:
            ok, _ = can_dispatch_to_device(preferred_device_id)
        if ok:
            return preferred_device_id

    try:
        Device = apps.get_model('main_page', 'Device')
        # 遍历所有已注册设备，使用实时内存状态判断，而不是仅依赖 DB 的 is_online 字段
        for device in Device.objects.all().order_by('device_id'):
            _auto_release_stale_busy_state(device.device_id)
            ok, _ = can_dispatch_to_device(device.device_id)
            if ok:
                return device.device_id
    except Exception as exc:
        print(f'Resolve dispatchable device failed: {exc}')

    return getattr(settings, 'MQTT_DEFAULT_DEVICE_ID', 'esp32_1')


def _set_device_task_status(device_id, new_status, current_task=None, reason=''):
    """统一更新设备任务状态并同步到数据库/WebSocket。"""
    state = _ensure_device_state(device_id)
    if state is None:
        return
    state['task_status'] = new_status
    if current_task is not None:
        state['current_task'] = current_task
    now = timezone.now()

    try:
        Device = apps.get_model('main_page', 'Device')
        Device.objects.filter(device_id=device_id).update(
            task_status=new_status,
            current_task=state['current_task'],
            updated_at=now,
        )
    except Exception as exc:
        print(f'Device task status DB update failed: {exc}')

    _broadcast('device_status', {
        'device_id': device_id,
        'payload': {
            'event': new_status,
            'is_online': state['is_online'],
            'task_status': new_status,
            'reason': reason,
        },
    })


def _abort_device_task(device_id, reason, triggered_by='system'):
    """中止设备当前任务：发送停止指令、置为 error 状态并广播。"""
    state = _ensure_device_state(device_id)
    if state is None:
        return

    # 向设备发送所有电机的停止指令（软停止）
    stop_results = []
    if client is not None and client.is_connected():
        topic = _device_control_topic(device_id)
        for motor in range(4):
            cmd = f'cmd_{motor}_0_0'
            try:
                info = client.publish(topic, cmd)
                stop_results.append({'motor': motor, 'rc': info.rc})
            except Exception as exc:
                stop_results.append({'motor': motor, 'error': str(exc)})

    _set_device_task_status(device_id, 'error', current_task={}, reason=reason)
    state = _ensure_device_state(device_id)
    if state is not None:
        state['active_motors'] = set()
    print(f'Device {device_id} task aborted: {reason}')


def acknowledge_device(device_ids, acknowledged_by=''):
    """用户确认设备问题已清除或任务已验收，将状态从 error/completed/estopped 恢复为 idle。"""
    results = []
    for device_id in device_ids:
        state = _ensure_device_state(device_id)
        if state is None:
            results.append({'device_id': device_id, 'success': False, 'error': 'Unknown device'})
            continue

        task_status = state.get('task_status', 'idle')
        if task_status not in ('error', 'completed', 'estopped'):
            results.append({
                'device_id': device_id,
                'success': False,
                'error': f'Device status is {task_status}, no acknowledgement required.',
            })
            continue

        _set_device_task_status(device_id, 'idle', current_task={})
        state['active_motors'] = set()

        _broadcast('device_status', {
            'device_id': device_id,
            'payload': {
                'event': 'acknowledged',
                'is_online': state['is_online'],
                'task_status': 'idle',
            },
        })

        # 同步记录急停日志的 acknowledged（兼容 estopped 场景）
        if task_status == 'estopped':
            try:
                Device = apps.get_model('main_page', 'Device')
                EmergencyStopLog = apps.get_model('main_page', 'EmergencyStopLog')
                device_obj = Device.objects.filter(device_id=device_id).first()
                if device_obj:
                    EmergencyStopLog.objects.filter(
                        device=device_obj,
                        acknowledged_at__isnull=True
                    ).update(
                        acknowledged_at=timezone.now(),
                        acknowledged_by=acknowledged_by,
                    )
            except Exception as exc:
                print(f'Acknowledge emergency stop log failed: {exc}')

        results.append({'device_id': device_id, 'success': True, 'task_status': 'idle'})

    return results


def _update_device_heartbeat(device_id):
    """更新设备心跳状态并广播。"""
    state = _ensure_device_state(device_id)
    if state is None:
        return
    now = timezone.now()

    with _device_states_lock:
        was_online = state['is_online']
        state['last_heartbeat'] = now
        state['is_online'] = True
        current_task_status = state['task_status']

    # 同步到数据库（在锁外执行，避免阻塞 MQTT 消息线程）
    try:
        Device = apps.get_model('main_page', 'Device')
        Device.objects.filter(device_id=device_id).update(
            is_online=True,
            last_heartbeat=now,
            updated_at=now,
        )
    except Exception as exc:
        print(f'Device heartbeat DB update failed: {exc}')

    if not was_online:
        _broadcast('device_status', {
            'device_id': device_id,
            'payload': {'event': 'online', 'is_online': True, 'task_status': current_task_status},
        })


def _mark_device_offline(device_id):
    """标记设备离线并广播。"""
    state = _ensure_device_state(device_id)
    if state is None:
        return

    with _device_states_lock:
        was_online = state['is_online']
        task_status = state['task_status']
        state['is_online'] = False
        # 离线时清零所有电机的 RPM 与健康状态，避免前端显示过期数据
        for motor_key in state.get('telemetry', {}):
            state['telemetry'][motor_key]['rpm'] = 0
            state['telemetry'][motor_key]['health_status'] = 'idle'
            state['telemetry'][motor_key]['zero_samples'] = 0

    try:
        Device = apps.get_model('main_page', 'Device')
        Device.objects.filter(device_id=device_id).update(
            is_online=False,
            telemetry=state.get('telemetry', {}),
            updated_at=timezone.now(),
        )
    except Exception as exc:
        print(f'Device offline DB update failed: {exc}')

    if was_online:
        _broadcast('device_status', {
            'device_id': device_id,
            'payload': {'event': 'offline', 'is_online': False, 'task_status': task_status},
        })


def _offline_detector():
    """后台线程：定期检查设备是否超时离线。"""
    while True:
        time.sleep(15)
        try:
            now = timezone.now()
            offline_candidates = []
            with _device_states_lock:
                for device_id, state in list(_device_states.items()):
                    last = state.get('last_heartbeat')
                    if last and state.get('is_online') and (now - last).total_seconds() > HEARTBEAT_TIMEOUT_SECONDS:
                        offline_candidates.append((device_id, state.get('task_status')))

            for device_id, task_status in offline_candidates:
                _mark_device_offline(device_id)
                # 若设备正在执行任务时掉线，自动中止任务并置为 error
                if task_status == 'busy':
                    _abort_device_task(device_id, reason='heartbeat_timeout', triggered_by='system')
        except Exception as exc:
            print(f'Offline detector error: {exc}')


# 启动离线检测线程（守护线程）
_offline_thread = threading.Thread(target=_offline_detector, daemon=True)
_offline_thread.start()


def on_connect(mqtt_client, userdata, flags, rc):
    if rc == 0:
        print("MQTT Connect Success!")
        # 使用通配符订阅所有 esp32_N 设备
        mqtt_client.subscribe('esp32/+/+')
        # 兼容旧设备的硬编码 topic（单台旧 ESP32）
        mqtt_client.subscribe('esp32_1/+')
        _set_mqtt_connection_state(True)
    else:
        print("Bad Connection Code: ", rc)
        _set_mqtt_connection_state(False, reason=f'bad_connection_code_{rc}')


def on_disconnect(mqtt_client, userdata, rc):
    reason = f'disconnect_rc_{rc}' if rc is not None else 'unexpected_disconnect'
    print(f"MQTT Disconnected: {reason}")
    _set_mqtt_connection_state(False, reason=reason)


def _mqtt_connection_watchdog():
    """守护线程：定期校验 client.is_connected() 与内存状态是否一致，并在需要时触发自动重连。"""
    while True:
        time.sleep(5)
        try:
            expected = client is not None and client.is_connected()
            with _mqtt_connection_lock:
                current = _mqtt_connection_state.get('connected', False)
            if current != expected:
                _set_mqtt_connection_state(expected, reason='watchdog_reconcile')

            # 自动重连：仅在未连接且启用时执行
            if not expected and _auto_reconnect_state['enabled']:
                with _auto_reconnect_lock:
                    next_attempt_at = _auto_reconnect_state['next_attempt_at']
                    in_progress = _auto_reconnect_state['in_progress']

                if not in_progress:
                    now = time.time()
                    if next_attempt_at is None:
                        _schedule_next_auto_reconnect(reason='watchdog_no_schedule')
                    elif now >= next_attempt_at:
                        _do_auto_reconnect()
        except Exception as exc:
            print(f'MQTT connection watchdog error: {exc}')


# 启动 MQTT 连接状态看门狗线程（守护线程）
_mqtt_watchdog_thread = threading.Thread(target=_mqtt_connection_watchdog, daemon=True)
_mqtt_watchdog_thread.start()


# Django 存储方法
# Device事件开始
def device_event_start(device_id, motor, speed, time):
    global ongoing_events
    # objects.create()方法返回一个新建立的object
    device_event = MotorEvent.objects.create(
        device_id=device_id,
        motor=motor,
        speed=speed,
        time=time,
    )
    ongoing_events.append(device_event)


# Motor接收数据
def device_data(device_id, motor, data_type, data):
    global ongoing_events
    for event in ongoing_events:
        # 判定当前接收数据与正在进行事件列表中哪一个事件契合
        if event.motor == motor and event.device_id == device_id:
            MotorData.objects.create(
                parent_event_id=event,
                motor_id=motor,
                data_type=data_type,
                data=data
            )
        else:
            pass


# Device事件结束
def device_event_done(device_id, motor):
    global ongoing_events
    tmp_array = []
    for event in ongoing_events:
        if event.motor == motor and event.device_id == device_id:
            # 更新事件状态
            event.statue = 2
            event.save()
        else:
            # 保留
            tmp_array.append(event)
    # 更新仍在进行的事件列表
    ongoing_events = tmp_array


MOTOR_HEALTH_ZERO_THRESHOLD = 3


def _match_spinning_record(device_id, motor_index, speed, duration, expected_status):
    """根据设备、电机索引、速度、时长和期望状态匹配最新的 Spinning 记录。"""
    try:
        motor = Motor.objects.filter(motor_index=motor_index).first()
        motor_name = motor.name if motor else ''
        filters = {
            'device_id': device_id,
            'motor_name': motor_name,
            'motor_speed': speed,
            'duration_sec': duration,
        }
        if isinstance(expected_status, (tuple, list)):
            filters['status__in'] = expected_status
        else:
            filters['status'] = expected_status
        return Spinning.objects.filter(**filters).order_by('-scheduled_time').first()
    except Exception as exc:
        print(f'Match spinning record failed: {exc}')
        return None


def _update_spinning_status(device_id, motor_index, speed, duration, new_status):
    """把对应 Spinning 记录更新为 RUNNING 或 FINISHED。"""
    expected_map = {
        'RUNNING': 'SENT',
        'FINISHED': ('RUNNING', 'SENT'),
    }
    record = _match_spinning_record(
        device_id, motor_index, speed, duration, expected_map.get(new_status, new_status)
    )
    if record is None:
        return

    now = timezone.now()
    update_fields = {'status': new_status, 'updated_at': now}
    if new_status == 'RUNNING':
        update_fields['started_at'] = now
    elif new_status == 'FINISHED':
        update_fields['finished_at'] = now

    Spinning.objects.filter(id=record.id).update(**update_fields)
    print(f'Spinning record {record.id} status updated to {new_status}')


def _finish_stale_spinning_records(device_id, running_motors, reason='auto_release'):
    """当设备 busy 状态超时被自动释放时，将关联的 SENT/RUNNING Spinning 记录置为 FINISHED。"""
    try:
        motor_names = set()
        for motor_index in running_motors:
            motor = Motor.objects.filter(motor_index=motor_index).first()
            if motor:
                motor_names.add(motor.name)
        if not motor_names:
            return

        now = timezone.now()
        records = Spinning.objects.filter(
            device_id=device_id,
            status__in=('SENT', 'RUNNING'),
        ).filter(
            models.Q(motor_name__in=motor_names) |
            models.Q(motor_names__overlap=list(motor_names))
        )
        updated = records.update(
            status='FINISHED',
            finished_at=now,
            error_message=f'Finished by {reason}: task_finished not received within timeout',
            updated_at=now,
        )
        if updated:
            print(f'Finished {updated} stale Spinning record(s) for {device_id}')
    except Exception as exc:
        print(f'Finish stale spinning records failed: {exc}')


def _update_motor_health(device_id, motor, rpm):
    """根据目标转速与实际转速判断电机健康状态（idle / running / fault）。

    使用 active_motors 集合判断电机是否处于目标运行状态，支持多电机并发。
    """
    state = _ensure_device_state(device_id)
    if state is None:
        return
    motor_key = f'motor_{motor}'
    telemetry = state.setdefault('telemetry', {}).setdefault(motor_key, {})
    current_task = state.get('current_task') or {}
    active_motors = state.get('active_motors', set())

    is_target_motor = motor in active_motors
    target_speed = int(current_task.get('speed', 0)) if is_target_motor else 0

    if is_target_motor and target_speed > 0:
        if rpm == 0:
            telemetry['zero_samples'] = telemetry.get('zero_samples', 0) + 1
        else:
            telemetry['zero_samples'] = 0

        if telemetry.get('zero_samples', 0) >= MOTOR_HEALTH_ZERO_THRESHOLD:
            telemetry['health_status'] = 'fault'
        else:
            telemetry['health_status'] = 'running'
    else:
        telemetry['zero_samples'] = 0
        telemetry['health_status'] = 'idle'
        # 非目标电机收到转速消息时清零 RPM，避免任务结束后仍显示旧值
        telemetry['rpm'] = 0

    try:
        Device = apps.get_model('main_page', 'Device')
        Device.objects.filter(device_id=device_id).update(
            telemetry=state['telemetry'],
            updated_at=timezone.now(),
        )
    except Exception as exc:
        print(f'Device health telemetry DB update failed: {exc}')


def _update_device_task(device_id, motor, speed, duration, event_type):
    """更新内存中的设备任务状态并同步到数据库。

    支持多电机并发：使用 active_motors 集合跟踪当前仍在运行的电机，
    仅当所有电机都完成任务后才将设备状态恢复为 idle。
    """
    state = _ensure_device_state(device_id)
    if state is None:
        return
    now = timezone.now()
    active_motors = state.setdefault('active_motors', set())

    if event_type == 'create':
        active_motors.add(motor)
        state['task_status'] = 'busy'
        state['current_task'] = {
            'motor': motor,
            'speed': speed,
            'duration_sec': duration,
            'started_at': now.isoformat(),
            'expected_finished_at': (now + timedelta(seconds=duration)).isoformat(),
        }
    elif event_type == 'finished':
        active_motors.discard(motor)
        if not active_motors:
            state['task_status'] = 'idle'
            state['current_task'] = {}
        # 若仍有电机在运行，保持 busy 与 current_task 不变

        # 任务结束：将该电机的 RPM 清零并标记为 idle，避免前端显示旧值
        telemetry = state.setdefault('telemetry', {})
        motor_key = f'motor_{motor}'
        if motor_key in telemetry:
            telemetry[motor_key]['rpm'] = 0
            telemetry[motor_key]['health_status'] = 'idle'
            telemetry[motor_key]['zero_samples'] = 0

    # 同步数据库
    try:
        Device = apps.get_model('main_page', 'Device')
        Device.objects.filter(device_id=device_id).update(
            task_status=state['task_status'],
            current_task=state['current_task'],
            updated_at=now,
        )
    except Exception as exc:
        print(f'Device task DB update failed: {exc}')


def _update_device_telemetry(device_id, motor, key, value):
    """更新内存中的遥测数据并同步到数据库。"""
    state = _ensure_device_state(device_id)
    if state is None:
        return
    if 'telemetry' not in state:
        state['telemetry'] = {}
    motor_key = f'motor_{motor}'
    if motor_key not in state['telemetry']:
        state['telemetry'][motor_key] = {}
    state['telemetry'][motor_key][key] = value

    try:
        Device = apps.get_model('main_page', 'Device')
        Device.objects.filter(device_id=device_id).update(
            telemetry=state['telemetry'],
            updated_at=timezone.now(),
        )
    except Exception as exc:
        print(f'Device telemetry DB update failed: {exc}')


def _extract_device_metadata(envelope):
    device = envelope.get('device') or {}
    return (
        device.get('type') or envelope.get('device_type'),
        str(device.get('id') or envelope.get('device_id') or '') or None,
    )


def process_device_reply_envelope(topic, envelope):
    def _on_step_done(job):
        dispatch_ready_steps(
            job,
            resolve_dispatch_command=lambda step_execution: default_step_executor_registry.resolve_dispatch(
                step_execution,
                default_control_topic=_device_control_topic(orchestration_default_device_id()),
            ),
            dispatch_transport_message=orchestration_dispatch_transport_message,
            can_dispatch_to_device=can_dispatch_to_device,
            extract_device_id_from_topic=orchestration_extract_device_id_from_topic,
            default_device_id=orchestration_default_device_id(),
        )

    return handle_device_reply(
        topic,
        envelope,
        extract_device_metadata=_extract_device_metadata,
        on_step_done=_on_step_done,
    )


def on_message(mqtt_client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()
    device_id = _extract_device_id_from_topic(topic)

    # 处理心跳：任何来自 esp32_N/heartbeat 或 esp32_N/data 的消息都视为活跃信号
    # （当前固件 heartbeat 较稀疏，data 更频繁，因此用 data 辅助保活）
    if device_id:
        _update_device_heartbeat(device_id)

    # JSON 结构化设备回复（Recipe/Job 系统）
    if payload.startswith('{'):
        try:
            envelope = json.loads(payload)
            interface_type = envelope.get('interface_type')
            if interface_type in ['service', 'action']:
                package = process_device_reply_envelope(topic, envelope)
                package['device_id'] = device_id or package.get('device_id')
                _broadcast('device_reply', package)
                return
        except (json.JSONDecodeError, ValueError):
            pass

    # Legacy 文本协议处理，统一包装为标准化消息
    # MQTT指令信号: cmd_motor_speed_time
    if payload.startswith('cmd_'):
        try:
            inner = payload.replace('cmd_', '').strip()
            parts = inner.split('_')
            if len(parts) >= 3:
                motor = int(parts[0])
                speed = int(parts[1])
                duration = int(parts[2])
                _broadcast('cmd', {
                    'device_id': device_id or 'esp32_1',
                    'payload': {'motor': motor, 'speed': speed, 'duration_sec': duration},
                })
        except Exception as exc:
            print(f'Failed to parse cmd payload: {payload}, error: {exc}')

    # ESP32反馈PCNT数据: pcnt_count_motor_data
    elif payload.startswith('pcnt_count_'):
        try:
            inner = payload.replace('pcnt_count_', '').strip()
            parts = inner.split('_')
            if len(parts) >= 2:
                motor = int(parts[0])
                count = int(parts[1])
                effective_device_id = device_id or 'esp32_1'
                device_data(effective_device_id, motor, 1, count)
                _update_device_telemetry(effective_device_id, motor, 'pcnt', count)
                _broadcast('telemetry', {
                    'device_id': effective_device_id,
                    'payload': {'motor': motor, 'pcnt': count, 'telemetry_type': 'pcnt'},
                })
        except Exception as exc:
            print(f'Failed to parse pcnt payload: {payload}, error: {exc}')

    # ESP32反馈PCNT转速: pcnt_rpm_motor_rpm
    elif payload.startswith('pcnt_rpm_'):
        try:
            inner = payload.replace('pcnt_rpm_', '').strip()
            parts = inner.split('_')
            if len(parts) >= 2:
                motor = int(parts[0])
                rpm = int(parts[1])
                effective_device_id = device_id or 'esp32_1'
                _update_device_telemetry(effective_device_id, motor, 'rpm', rpm)
                _update_motor_health(effective_device_id, motor, rpm)
                _broadcast('telemetry', {
                    'device_id': effective_device_id,
                    'payload': {'motor': motor, 'rpm': rpm, 'telemetry_type': 'rpm'},
                })
        except Exception as exc:
            print(f'Failed to parse pcnt_rpm payload: {payload}, error: {exc}')

    # ESP32反馈PWM数据: pwm_set_motor_data
    elif payload.startswith('pwm_set_'):
        try:
            inner = payload.replace('pwm_set_', '').strip()
            parts = inner.split('_')
            if len(parts) >= 2:
                motor = int(parts[0])
                count = int(parts[1])
                effective_device_id = device_id or 'esp32_1'
                device_data(effective_device_id, motor, 2, count)
                _update_device_telemetry(effective_device_id, motor, 'pwm', count)
                _broadcast('telemetry', {
                    'device_id': effective_device_id,
                    'payload': {'motor': motor, 'pwm': count, 'telemetry_type': 'pwm'},
                })
        except Exception as exc:
            print(f'Failed to parse pwm payload: {payload}, error: {exc}')

    # ESP32反馈任务相关信号
    # task_create_motor_speed_time
    # task_finished_motor_speed_time
    elif payload.startswith('task_'):
        try:
            inner = payload.replace('task_', '').strip()
            effective_device_id = device_id or 'esp32_1'
            if inner.startswith('create_'):
                inner = inner.replace('create_', '').strip()
                parts = inner.split('_')
                if len(parts) >= 3:
                    motor = int(parts[0])
                    speed = int(parts[1])
                    duration = int(parts[2])
                    device_event_start(effective_device_id, motor, speed, duration)
                    _update_device_task(effective_device_id, motor, speed, duration, 'create')
                    _update_spinning_status(effective_device_id, motor, speed, duration, 'RUNNING')
                    _broadcast('task_status', {
                        'device_id': effective_device_id,
                        'payload': {
                            'event': 'task_create',
                            'motor': motor,
                            'speed': speed,
                            'duration_sec': duration,
                        },
                    })
            elif inner.startswith('finished_'):
                inner = inner.replace('finished_', '').strip()
                parts = inner.split('_')
                if len(parts) >= 3:
                    motor = int(parts[0])
                    speed = int(parts[1])
                    duration = int(parts[2])
                    device_event_done(effective_device_id, motor)
                    # 更新设备任务状态、active_motors，并清零该电机的 RPM
                    _update_device_task(effective_device_id, motor, speed, duration, 'finished')
                    _update_spinning_status(effective_device_id, motor, speed, duration, 'FINISHED')
                    _broadcast('task_status', {
                        'device_id': effective_device_id,
                        'payload': {
                            'event': 'task_completed_pending_ack',
                            'motor': motor,
                            'message': 'Task completed. Waiting for operator acknowledgement.',
                        },
                    })
        except Exception as exc:
            print(f'Failed to parse task payload: {payload}, error: {exc}')

    # 心跳文本（当前固件发 "ESP32_1 is online"）
    elif 'online' in payload.lower():
        if device_id:
            _broadcast('heartbeat', {
                'device_id': device_id,
                'payload': {'message': payload, 'is_online': True},
            })


# ---------------------------------------------------------------------------
# 急停与恢复接口（方案 A：软急停，兼容当前无急停逻辑的 ESP32 固件）
# ---------------------------------------------------------------------------

def emergency_stop(device_ids, triggered_by='', reason='', scope='single'):
    """
    向指定设备发送软急停指令：将所有电机速度设为 0。
    同时在前端/后端标记设备为 estopped，阻止后续任务下发直到恢复。
    """
    results = []
    for device_id in device_ids:
        state = _ensure_device_state(device_id)
        if state is None:
            results.append({'device_id': device_id, 'success': False, 'error': 'Unknown device'})
            continue

        # 向设备发送所有电机的停止指令
        stop_results = []
        if client is not None and client.is_connected():
            topic = _device_control_topic(device_id)
            for motor in range(4):
                cmd = f'cmd_{motor}_0_0'
                try:
                    info = client.publish(topic, cmd)
                    stop_results.append({'motor': motor, 'rc': info.rc})
                except Exception as exc:
                    stop_results.append({'motor': motor, 'error': str(exc)})
        else:
            stop_results.append({'error': 'MQTT client unavailable'})

        # 更新内存与数据库状态
        state['task_status'] = 'estopped'
        state['current_task'] = {}
        try:
            Device = apps.get_model('main_page', 'Device')
            Device.objects.filter(device_id=device_id).update(
                task_status='estopped',
                current_task={},
                updated_at=timezone.now(),
            )
            EmergencyStopLog = apps.get_model('main_page', 'EmergencyStopLog')
            device_obj = Device.objects.filter(device_id=device_id).first()
            if device_obj:
                EmergencyStopLog.objects.create(
                    device=device_obj,
                    triggered_by=triggered_by,
                    scope=scope,
                    reason=reason,
                )
        except Exception as exc:
            print(f'Emergency stop DB update failed: {exc}')

        _broadcast('device_status', {
            'device_id': device_id,
            'payload': {
                'event': 'estopped',
                'is_online': state['is_online'],
                'task_status': 'estopped',
                'stop_results': stop_results,
            },
        })

        results.append({
            'device_id': device_id,
            'success': True,
            'task_status': 'estopped',
            'stop_results': stop_results,
        })

    return results


def resume_devices(device_ids, resumed_by=''):
    """恢复设备任务下发能力：将设备状态从 estopped 重置为 idle。"""
    results = []
    for device_id in device_ids:
        state = _ensure_device_state(device_id)
        if state is None:
            results.append({'device_id': device_id, 'success': False, 'error': 'Unknown device'})
            continue

        state['task_status'] = 'idle'
        try:
            Device = apps.get_model('main_page', 'Device')
            Device.objects.filter(device_id=device_id).update(
                task_status='idle',
                updated_at=timezone.now(),
            )
            EmergencyStopLog = apps.get_model('main_page', 'EmergencyStopLog')
            device_obj = Device.objects.filter(device_id=device_id).first()
            if device_obj:
                EmergencyStopLog.objects.filter(
                    device=device_obj,
                    acknowledged_at__isnull=True
                ).update(
                    acknowledged_at=timezone.now(),
                    acknowledged_by=resumed_by,
                )
        except Exception as exc:
            print(f'Resume device DB update failed: {exc}')

        _broadcast('device_status', {
            'device_id': device_id,
            'payload': {
                'event': 'resumed',
                'is_online': state['is_online'],
                'task_status': 'idle',
            },
        })

        results.append({'device_id': device_id, 'success': True, 'task_status': 'idle'})

    return results


def dispatch_motor_task(device_id, motor, speed, duration, check_dispatch=True):
    """向指定设备下发电机任务。

    参数 check_dispatch：默认 True，下发前检查设备在线与电机空闲状态；
    用于多电机调度时，首个电机已确认可下发，后续电机直接发布命令。
    """
    if check_dispatch:
        ok, reason = can_dispatch_motor(device_id, motor)
        if not ok:
            return {'success': False, 'error': reason}
    if client is None or not client.is_connected():
        return {'success': False, 'error': 'MQTT client unavailable'}

    topic = _device_control_topic(device_id)
    cmd = f'cmd_{motor}_{speed}_{duration}'
    now = timezone.now()
    expected_finished_at = now + timedelta(seconds=duration)

    # 乐观置为 busy，防止并发下发；设备后续上报 task_create 时会再次刷新 current_task
    _set_device_task_status(
        device_id,
        'busy',
        current_task={
            'motor': motor,
            'speed': speed,
            'duration_sec': duration,
            'started_at': now.isoformat(),
            'expected_finished_at': expected_finished_at.isoformat(),
        },
    )

    # 乐观加入 active_motors，防止任务创建消息到达前重复下发同一电机
    state = _ensure_device_state(device_id)
    if state is not None:
        state.setdefault('active_motors', set()).add(motor)

    try:
        info = client.publish(topic, cmd)
        return {'success': True, 'topic': topic, 'command': cmd, 'rc': info.rc}
    except Exception as exc:
        # 下发失败回滚为 idle 并移出 active_motors，避免一直占用
        _set_device_task_status(device_id, 'idle', current_task={})
        if state is not None:
            state['active_motors'].discard(motor)
        return {'success': False, 'error': str(exc)}


def get_device_states():
    """获取当前所有设备的内存状态快照（用于 API 和 WebSocket 初始化）。"""
    with _device_states_lock:
        states = dict(_device_states)
    # 将不可 JSON 序列化的 set 转换为 list，避免 WebSocket/API 序列化失败
    serializable = {}
    for device_id, state in states.items():
        copy = dict(state)
        if isinstance(copy.get('active_motors'), set):
            copy['active_motors'] = sorted(copy['active_motors'])
        serializable[device_id] = copy
    return serializable


def publish_device_command(topic, payload):
    if client is None:
        raise RuntimeError('MQTT client is unavailable.')

    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload)
    else:
        payload = str(payload)

    message_info = client.publish(topic, payload)
    return message_info


def mqtt_client_available():
    return client is not None and client.is_connected()


def _perform_reconnect():
    """实际的 MQTT 重连逻辑（被手动重连与自动重连共用）。"""
    global client
    try:
        if client is not None and client.is_connected():
            return {'success': True, 'connected': True, 'message': 'Already connected'}

        if client is not None:
            # 复用现有 client，触发 paho 立即重连
            client.reconnect()
        else:
            # client 为 None（如启动失败），重新初始化
            client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
                reconnect_on_failure=True,
            )
            client.on_connect = on_connect
            client.on_disconnect = on_disconnect
            client.on_message = on_message
            client.reconnect_delay_set(min_delay=1, max_delay=30)
            client.username_pw_set(settings.MQTT_USER, settings.MQTT_PASSWORD)
            client.connect(
                host=settings.MQTT_SERVER,
                port=settings.MQTT_PORT,
                keepalive=settings.MQTT_KEEPALIVE
            )
            client.loop_start()

        # 最多等待 3 秒让连接建立（paho loop 线程在后台完成握手）
        deadline = time.time() + 3
        while time.time() < deadline:
            if client.is_connected():
                break
            time.sleep(0.1)

        connected = client.is_connected()
        message = 'MQTT connected' if connected else 'MQTT reconnection in progress, please wait'
        return {'success': True, 'connected': connected, 'message': message}
    except Exception as exc:
        print(f'MQTT reconnect failed: {exc}')
        return {'success': False, 'connected': False, 'error': str(exc)}


def reconnect_mqtt_client():
    """手动重连 MQTT Broker；供前端刷新按钮或管理接口调用。调用后重置自动重连退避。"""
    _reset_auto_reconnect()
    return _perform_reconnect()


def _should_init_mqtt_client():
    """判断当前进程是否应该创建 MQTT Client。

    - runserver 自动重载子进程会设置 RUN_MAIN，在此处创建 Client。
    - Daphne / uvicorn / gunicorn 等 ASGI 服务器没有 RUN_MAIN，也需要创建 Client。
    - 管理命令（migrate/test/shell）不需要创建 Client。
    """
    if os.environ.get('RUN_MAIN'):
        return True
    if any('daphne' in arg or 'uvicorn' in arg or 'gunicorn' in arg for arg in sys.argv):
        return True
    return False


if _should_init_mqtt_client():
    # 先创建 client 对象并注册回调；即使初始连接失败也保留该对象，
    # 由 apps.py 的 loop_start() 与看门狗的自动重连逻辑在后台继续尝试，
    # 避免重新创建 client 对象导致其它地方持有的引用失效。
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
        reconnect_on_failure=True,
    )
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.username_pw_set(settings.MQTT_USER, settings.MQTT_PASSWORD)
    try:
        client.connect(
            host=settings.MQTT_SERVER,
            port=settings.MQTT_PORT,
            keepalive=settings.MQTT_KEEPALIVE
        )
    except (OSError, TimeoutError, socket.error) as exc:
        _set_mqtt_connection_state(False, reason=f'startup_failed_{exc}')
        print(f"MQTT unavailable during Django startup, will retry via auto-reconnect: {exc}")


# 仅在需要 MQTT 客户端的进程中启用自动重连，避免测试/迁移等进程发起无意义的网络重试
_auto_reconnect_state['enabled'] = _should_init_mqtt_client()
if _auto_reconnect_state['enabled'] and (client is None or not client.is_connected()):
    _schedule_next_auto_reconnect(reason='startup_not_connected')
