import logging
import threading
import time

from django.conf import settings
from django.db import close_old_connections

from ..models import BatchJob
from .dispatch_runtime import (
    default_control_topic,
    default_device_id,
    dispatch_transport_message,
    extract_device_id_from_topic,
)
from .enums import JobStatus
from .service import check_internal_waits, check_job_timeouts, check_timed_device_steps
from .step_executors import default_step_executor_registry

logger = logging.getLogger(__name__)

ORCHESTRATION_POLL_INTERVAL_SECONDS = getattr(settings, 'ORCHESTRATION_POLL_INTERVAL_SECONDS', 0.5)


class OrchestrationScheduler:
    """后台推进 Recipe/BatchJob 状态机，避免依赖前端轮询 status 接口。"""

    _instance_lock = threading.Lock()
    _thread = None
    _stop_event = threading.Event()

    @classmethod
    def start(cls):
        with cls._instance_lock:
            if cls._thread is not None and cls._thread.is_alive():
                logger.info('OrchestrationScheduler already running')
                return
            cls._stop_event.clear()
            cls._thread = threading.Thread(
                target=cls._run,
                daemon=True,
                name='OrchestrationScheduler',
            )
            cls._thread.start()
            print('OrchestrationScheduler started')

    @classmethod
    def stop(cls):
        cls._stop_event.set()
        if cls._thread is not None:
            cls._thread.join(timeout=2)

    @classmethod
    def _run(cls):
        while not cls._stop_event.is_set():
            close_old_connections()
            try:
                cls.process_running_jobs()
            except Exception as exc:
                logger.exception('OrchestrationScheduler error: %s', exc)
            time.sleep(ORCHESTRATION_POLL_INTERVAL_SECONDS)

    @classmethod
    def process_running_jobs(cls):
        jobs = BatchJob.objects.filter(status=JobStatus.RUNNING.value).order_by('id')
        for job in jobs:
            cls.process_job(job)

    @classmethod
    def process_job(cls, job):
        kwargs = {
            'resolve_dispatch_command': lambda step_execution: default_step_executor_registry.resolve_dispatch(
                step_execution,
                default_control_topic=default_control_topic(),
            ),
            'dispatch_transport_message': dispatch_transport_message,
            'can_dispatch_to_device': cls._can_dispatch_to_device,
            'extract_device_id_from_topic': extract_device_id_from_topic,
            'default_device_id': default_device_id(),
        }
        check_internal_waits(job, **kwargs)
        check_timed_device_steps(job, **kwargs)
        check_job_timeouts(job)

    @staticmethod
    def _can_dispatch_to_device(device_id):
        from ..mqtt import can_dispatch_to_device

        return can_dispatch_to_device(device_id)
