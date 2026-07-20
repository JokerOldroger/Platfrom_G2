from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from ..models import BatchJob, BatchStepExecution, CommandOutbox, TelemetryIngest
from .enums import JobStatus, OutboxStatus, StepStatus
from .events import DeviceReplyEvent
from .transitions import derive_job_status, transition_outbox_status, transition_step_status


VALID_REPLY_INTERFACES = ['service', 'action']
VALID_REPLY_MESSAGE_TYPES = ['ack', 'progress', 'result', 'error']


@dataclass
class JobStartResult:
    job: BatchJob
    dispatched_messages: list
    failed_steps: list


@dataclass
class JobResumeResult:
    job: BatchJob
    resumed_steps: list
    dispatched_messages: list
    failed_steps: list


@dataclass
class TimeoutCheckResult:
    checked_steps: int
    timed_out_steps: list


def _step_parameters(step_execution):
    return (step_execution.command_payload or {}).get('parameters') or {}


def _step_timeout_sec(step_execution):
    parameters = _step_parameters(step_execution)
    timeout_sec = parameters.get('timeout_sec')
    if timeout_sec is not None:
        return int(timeout_sec)
    if step_execution.recipe_step and step_execution.recipe_step.expected_duration_sec:
        return int(step_execution.recipe_step.expected_duration_sec)
    return None


def _step_depends_on(step_execution, step_lookup):
    parameters = _step_parameters(step_execution)
    dependencies = parameters.get('depends_on_steps') or []
    if dependencies:
        return [int(item) for item in dependencies]

    if parameters.get('wait_for_previous'):
        current_step_no = (step_execution.command_payload or {}).get('step_no')
        if current_step_no is None:
            return []
        return sorted([step_no for step_no in step_lookup.keys() if step_no < current_step_no])

    return []


def _is_terminal(status):
    return status in [StepStatus.DONE.value, StepStatus.FAILED.value, StepStatus.SKIPPED.value]


def _step_resource_locks(step_execution):
    parameters = _step_parameters(step_execution)
    explicit_locks = parameters.get('resource_locks') or []
    if explicit_locks:
        return [str(lock) for lock in explicit_locks if str(lock).strip()]

    device = parameters.get('device')
    device_id = str(parameters.get('device_id') or '').strip()
    step_type = (step_execution.command_payload or {}).get('step_type')

    if isinstance(device, dict):
        device_type = str(device.get('type') or 'generic').strip()
        device_id = str(device.get('id') or device_id).strip()
        if device_id:
            return [f'{device_type}:{device_id}']
        return [f'{device_type}:shared']

    if device:
        device_type = str(device).strip()
        if device_id:
            return [f'{device_type}:{device_id}']
        return [f'{device_type}:shared']

    # 缺省推导：机械臂默认独占，WAIT 默认不占锁，其它类型在未声明设备时不强制占锁。
    if step_type == 'MOVE_ARM':
        return [f'move_arm:{device_id or "shared"}']
    return []


def _active_job_locks(job, excluding_step_execution_ids=None):
    excluding_ids = set(excluding_step_execution_ids or [])
    active_steps = BatchStepExecution.objects.filter(
        job=job,
        status__in=[StepStatus.QUEUED.value, StepStatus.RUNNING.value],
    )
    active_locks = set()
    for step_execution in active_steps:
        if step_execution.id in excluding_ids:
            continue
        active_locks.update(_step_resource_locks(step_execution))
    return active_locks


def get_ready_pending_steps(job):
    step_executions = list(
        BatchStepExecution.objects.select_related('recipe_step').filter(job=job).order_by('recipe_step__step_no', 'id')
    )
    step_lookup = {}
    for step_execution in step_executions:
        step_no = (step_execution.command_payload or {}).get('step_no')
        if step_no is not None:
            step_lookup[int(step_no)] = step_execution

    ready_steps = []
    active_locks = _active_job_locks(job)
    reserved_locks = set()
    for step_execution in step_executions:
        if step_execution.status != StepStatus.PENDING.value:
            continue
        dependency_step_nos = _step_depends_on(step_execution, step_lookup)
        dependencies_ready = not dependency_step_nos or all(
            step_lookup.get(step_no) is not None and step_lookup[step_no].status == StepStatus.DONE.value
            for step_no in dependency_step_nos
        )
        if not dependencies_ready:
            continue

        required_locks = set(_step_resource_locks(step_execution))
        if required_locks & active_locks:
            continue
        if required_locks & reserved_locks:
            continue

        ready_steps.append(step_execution)
        reserved_locks.update(required_locks)
    return ready_steps


def _dispatch_single_step(
    *,
    job,
    step_execution,
    resolve_dispatch_command,
    dispatch_transport_message,
    can_dispatch_to_device,
    extract_device_id_from_topic,
    default_device_id,
):
    dispatch = resolve_dispatch_command(step_execution)

    if dispatch['transport'] == 'mqtt':
        device_id = extract_device_id_from_topic(dispatch['topic']) or default_device_id
        ok, reason = can_dispatch_to_device(device_id)
        if not ok:
            raise ValueError(reason)

    outbox = CommandOutbox.objects.create(
        job=job,
        step_execution=step_execution,
        topic=dispatch['topic'],
        payload={
            'interface_type': dispatch.get('interface_type'),
            'route_name': dispatch.get('route_name'),
            'transport': dispatch['transport'],
            'device': dispatch['device'],
            'command_type': dispatch['command_type'],
            'body': dispatch['payload'],
        },
        status=OutboxStatus.QUEUED.value,
    )
    dispatch_result = dispatch_transport_message(
        transport=dispatch['transport'],
        topic=dispatch['topic'],
        payload=dispatch['payload'],
        interface_type=dispatch.get('interface_type'),
        route_name=dispatch.get('route_name'),
        device=dispatch['device'],
        correlation={
            'job_id': job.id,
            'step_execution_id': step_execution.id,
            'outbox_id': outbox.id,
        },
    )
    if not dispatch_result.get('accepted', True):
        raise ValueError(dispatch_result.get('detail') or 'Bridge rejected dispatch.')

    outbox.status = OutboxStatus.SENT.value
    outbox.sent_at = timezone.now()
    outbox.save(update_fields=['status', 'sent_at', 'updated_at'])

    step_execution.status = StepStatus.RUNNING.value
    step_execution.started_at = timezone.now()
    step_execution.error_message = None
    step_execution.telemetry = {
        **(step_execution.telemetry or {}),
        'dispatch_topic': dispatch['topic'],
        'dispatch_payload': dispatch['payload'],
        'dispatch_transport': dispatch['transport'],
        'dispatch_interface_type': dispatch.get('interface_type'),
        'dispatch_route_name': dispatch.get('route_name'),
    }
    step_execution.save(update_fields=['status', 'started_at', 'error_message', 'telemetry', 'updated_at'])
    return outbox


def dispatch_ready_steps(
    job,
    *,
    resolve_dispatch_command,
    dispatch_transport_message,
    can_dispatch_to_device,
    extract_device_id_from_topic,
    default_device_id,
):
    dispatched_messages = []
    failed_steps = []

    ready_steps = get_ready_pending_steps(job)
    for step_execution in ready_steps:
        try:
            outbox = _dispatch_single_step(
                job=job,
                step_execution=step_execution,
                resolve_dispatch_command=resolve_dispatch_command,
                dispatch_transport_message=dispatch_transport_message,
                can_dispatch_to_device=can_dispatch_to_device,
                extract_device_id_from_topic=extract_device_id_from_topic,
                default_device_id=default_device_id,
            )
            dispatched_messages.append(outbox)
        except Exception as exc:
            step_execution.status = StepStatus.FAILED.value
            step_execution.error_message = str(exc)
            step_execution.save(update_fields=['status', 'error_message', 'updated_at'])
            failed_steps.append({
                'step_execution_id': step_execution.id,
                'step_no': step_execution.command_payload.get('step_no'),
                'error': str(exc),
            })

    if failed_steps and not dispatched_messages:
        job.status = JobStatus.FAILED.value
        job.error_message = 'Unable to dispatch any ready device commands.'
        if not job.finished_at:
            job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])

    return dispatched_messages, failed_steps


def start_job(
    job,
    *,
    resolve_dispatch_command,
    dispatch_transport_message,
    can_dispatch_to_device,
    extract_device_id_from_topic,
    default_device_id,
):
    if job.status not in [JobStatus.PENDING.value, JobStatus.PAUSED.value]:
        raise ValueError(f'Job cannot be started from status {job.status}.')

    dispatched_messages = []
    failed_steps = []

    with transaction.atomic():
        now = timezone.now()
        if not job.started_at:
            job.started_at = now
        job.status = JobStatus.RUNNING.value
        job.error_message = None
        job.save(update_fields=['status', 'error_message', 'started_at', 'updated_at'])
        dispatched_messages, failed_steps = dispatch_ready_steps(
            job,
            resolve_dispatch_command=resolve_dispatch_command,
            dispatch_transport_message=dispatch_transport_message,
            can_dispatch_to_device=can_dispatch_to_device,
            extract_device_id_from_topic=extract_device_id_from_topic,
            default_device_id=default_device_id,
        )

    return JobStartResult(job=job, dispatched_messages=dispatched_messages, failed_steps=failed_steps)


def resolve_envelope_context(envelope):
    correlation = envelope.get('correlation') or {}
    outbox = None
    step_execution = None
    job = None

    outbox_id = correlation.get('outbox_id')
    if outbox_id:
        try:
            outbox = CommandOutbox.objects.select_related('step_execution', 'job').get(id=outbox_id)
        except CommandOutbox.DoesNotExist:
            outbox = None

    step_execution_id = correlation.get('step_execution_id')
    if step_execution_id:
        try:
            step_execution = BatchStepExecution.objects.select_related('job').get(id=step_execution_id)
        except BatchStepExecution.DoesNotExist:
            step_execution = None

    job_id = correlation.get('job_id')
    if job_id:
        try:
            job = BatchJob.objects.get(id=job_id)
        except BatchJob.DoesNotExist:
            job = None

    if outbox is not None:
        if step_execution is None:
            step_execution = outbox.step_execution
        if job is None:
            job = outbox.job
    if step_execution is not None and job is None:
        job = step_execution.job

    return outbox, step_execution, job


def merge_step_telemetry(step_execution, envelope):
    step_execution.telemetry = {
        **(step_execution.telemetry or {}),
        'last_device_reply': envelope,
        'last_reply_at': timezone.now().isoformat(),
        'last_reply_status': envelope.get('status'),
        'last_reply_message_type': envelope.get('message_type'),
    }


def sync_job_status(job):
    if job is None:
        return

    step_statuses = list(BatchStepExecution.objects.filter(job=job).values_list('status', flat=True))
    next_status = derive_job_status(step_statuses, job.status)
    if next_status == job.status and not (
        next_status == JobStatus.DONE.value and job.finished_at is None
    ) and not (
        next_status == JobStatus.FAILED.value and job.finished_at is None
    ):
        return

    job.status = next_status
    update_fields = ['status', 'updated_at']
    if next_status in [JobStatus.DONE.value, JobStatus.FAILED.value] and not job.finished_at:
        job.finished_at = timezone.now()
        update_fields.append('finished_at')
    job.save(update_fields=update_fields)


def handle_device_reply(
    topic,
    envelope,
    *,
    extract_device_metadata,
    on_step_done=None,
):
    interface_type = envelope.get('interface_type')
    if interface_type not in VALID_REPLY_INTERFACES:
        raise ValueError('Unsupported interface_type in device reply envelope.')

    message_type = envelope.get('message_type')
    if message_type not in VALID_REPLY_MESSAGE_TYPES:
        raise ValueError('Unsupported message_type in device reply envelope.')

    outbox, step_execution, job = resolve_envelope_context(envelope)
    device_type, device_id = extract_device_metadata(envelope)
    event = DeviceReplyEvent(
        interface_type=interface_type,
        message_type=message_type,
        status=envelope.get('status'),
        error_message=(envelope.get('error') or {}).get('message') or envelope.get('message'),
    )

    telemetry = TelemetryIngest.objects.create(
        job=job,
        step_execution=step_execution,
        device_type=device_type,
        device_id=device_id,
        topic=topic,
        payload=envelope,
    )

    if outbox is not None:
        outbox.status = transition_outbox_status(outbox.status, event)
        if outbox.status == OutboxStatus.ACKED.value and not outbox.acked_at:
            outbox.acked_at = timezone.now()
        if outbox.status == OutboxStatus.FAILED.value:
            outbox.error_message = event.error_message
            outbox.save(update_fields=['status', 'error_message', 'updated_at'])
        else:
            outbox.save(update_fields=['status', 'acked_at', 'updated_at'])

    if step_execution is not None:
        merge_step_telemetry(step_execution, envelope)
        next_step_status = transition_step_status(step_execution.status, event)
        previous_step_status = step_execution.status
        if next_step_status != step_execution.status:
            step_execution.status = next_step_status
        if next_step_status in [StepStatus.RUNNING.value, StepStatus.DONE.value, StepStatus.FAILED.value]:
            if not step_execution.started_at:
                step_execution.started_at = timezone.now()
        if next_step_status in [StepStatus.DONE.value, StepStatus.FAILED.value]:
            step_execution.finished_at = timezone.now()
        if next_step_status == StepStatus.DONE.value:
            step_execution.error_message = None
        if next_step_status == StepStatus.FAILED.value:
            step_execution.error_message = event.error_message
        step_execution.save(
            update_fields=['status', 'started_at', 'finished_at', 'error_message', 'telemetry', 'updated_at']
        )

    sync_job_status(job)

    if (
        on_step_done is not None
        and step_execution is not None
        and previous_step_status != StepStatus.DONE.value
        and step_execution.status == StepStatus.DONE.value
        and job is not None
        and job.status == JobStatus.RUNNING.value
    ):
        on_step_done(job)

    return {
        'type': 'mqtt_msg_broadcast',
        'topic': 'device_reply',
        'interface_type': interface_type,
        'message_type': message_type,
        'status': envelope.get('status'),
        'route_name': envelope.get('route_name'),
        'device_type': device_type,
        'device_id': device_id,
        'job_id': job.id if job else None,
        'step_execution_id': step_execution.id if step_execution else None,
        'payload': envelope,
        'telemetry_id': telemetry.id,
    }


def check_job_timeouts(job):
    now = timezone.now()
    checked_steps = 0
    timed_out_steps = []

    with transaction.atomic():
        running_steps = list(
            BatchStepExecution.objects.select_related('recipe_step').filter(
                job=job,
                status__in=[StepStatus.QUEUED.value, StepStatus.RUNNING.value],
            )
        )
        for step_execution in running_steps:
            checked_steps += 1
            timeout_sec = _step_timeout_sec(step_execution)
            if timeout_sec is None:
                continue

            started_at = step_execution.started_at or step_execution.created_at
            elapsed = (now - started_at).total_seconds()
            if elapsed <= timeout_sec:
                continue

            step_execution.status = StepStatus.FAILED.value
            step_execution.finished_at = now
            step_execution.error_message = f'Execution timeout after {timeout_sec} seconds.'
            step_execution.telemetry = {
                **(step_execution.telemetry or {}),
                'timeout_detected_at': now.isoformat(),
                'timeout_sec': timeout_sec,
            }
            step_execution.save(
                update_fields=['status', 'finished_at', 'error_message', 'telemetry', 'updated_at']
            )
            timed_out_steps.append({
                'step_execution_id': step_execution.id,
                'step_no': step_execution.command_payload.get('step_no'),
                'timeout_sec': timeout_sec,
            })

        if timed_out_steps:
            job.status = JobStatus.PAUSED.value
            job.error_message = 'Job paused due to step timeout. Manual confirmation required before resume.'
            job.save(update_fields=['status', 'error_message', 'updated_at'])

    return TimeoutCheckResult(checked_steps=checked_steps, timed_out_steps=timed_out_steps)


def resume_job(
    job,
    *,
    resolve_dispatch_command,
    dispatch_transport_message,
    can_dispatch_to_device,
    extract_device_id_from_topic,
    default_device_id,
    step_execution_ids=None,
):
    if job.status not in [JobStatus.FAILED.value, JobStatus.PAUSED.value, JobStatus.PENDING.value]:
        raise ValueError(f'Job cannot be resumed from status {job.status}.')

    resumed_steps = []
    with transaction.atomic():
        candidates = BatchStepExecution.objects.filter(job=job, status=StepStatus.FAILED.value).order_by('id')
        if step_execution_ids:
            candidates = candidates.filter(id__in=step_execution_ids)

        for step_execution in candidates:
            step_execution.status = StepStatus.PENDING.value
            step_execution.error_message = None
            step_execution.finished_at = None
            step_execution.started_at = None
            step_execution.save(
                update_fields=['status', 'error_message', 'finished_at', 'started_at', 'updated_at']
            )
            resumed_steps.append(step_execution.id)

        if not resumed_steps and job.status == JobStatus.PAUSED.value:
            # 兼容：仅由于 pause 但无 failed step 时，允许直接恢复 ready pending steps
            resumed_steps = []

        job.status = JobStatus.RUNNING.value
        job.error_message = None
        job.finished_at = None
        job.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])

        dispatched_messages, failed_steps = dispatch_ready_steps(
            job,
            resolve_dispatch_command=resolve_dispatch_command,
            dispatch_transport_message=dispatch_transport_message,
            can_dispatch_to_device=can_dispatch_to_device,
            extract_device_id_from_topic=extract_device_id_from_topic,
            default_device_id=default_device_id,
        )

    return JobResumeResult(
        job=job,
        resumed_steps=resumed_steps,
        dispatched_messages=dispatched_messages,
        failed_steps=failed_steps,
    )
