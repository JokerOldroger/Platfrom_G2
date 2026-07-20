from .enums import JobStatus, OutboxStatus, StepStatus
from .events import DeviceReplyEvent


SUCCESS_STEP_STATUSES = {StepStatus.DONE.value}
TERMINAL_STEP_STATUSES = {StepStatus.DONE.value, StepStatus.FAILED.value, StepStatus.SKIPPED.value}


def transition_outbox_status(current_status, event: DeviceReplyEvent):
    if event.message_type == 'error' or event.status == 'failed':
        return OutboxStatus.FAILED.value
    if current_status == OutboxStatus.FAILED.value:
        return current_status
    return OutboxStatus.ACKED.value


def transition_step_status(current_status, event: DeviceReplyEvent):
    if event.message_type == 'ack' or event.status in ['accepted', 'queued']:
        if current_status == StepStatus.PENDING.value:
            return StepStatus.QUEUED.value
        if current_status != StepStatus.DONE.value:
            return StepStatus.RUNNING.value
        return current_status

    if event.message_type == 'progress' or event.status in ['running', 'executing']:
        return StepStatus.RUNNING.value

    if event.message_type == 'result' and event.status in ['succeeded', 'done', 'completed']:
        return StepStatus.DONE.value

    if event.message_type == 'error' or event.status == 'failed':
        return StepStatus.FAILED.value

    return current_status


def derive_job_status(step_statuses, current_status):
    if not step_statuses:
        return current_status

    if current_status == JobStatus.PAUSED.value:
        return current_status

    if StepStatus.FAILED.value in step_statuses:
        return JobStatus.FAILED.value

    unfinished = [status for status in step_statuses if status != StepStatus.DONE.value]
    if unfinished:
        return JobStatus.RUNNING.value

    return JobStatus.DONE.value
