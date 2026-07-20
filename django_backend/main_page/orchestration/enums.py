from enum import StrEnum


class JobStatus(StrEnum):
    PENDING = 'PENDING'
    RUNNING = 'RUNNING'
    PAUSED = 'PAUSED'
    DONE = 'DONE'
    FAILED = 'FAILED'
    ABORTED = 'ABORTED'


class StepStatus(StrEnum):
    PENDING = 'PENDING'
    QUEUED = 'QUEUED'
    RUNNING = 'RUNNING'
    DONE = 'DONE'
    FAILED = 'FAILED'
    SKIPPED = 'SKIPPED'


class OutboxStatus(StrEnum):
    QUEUED = 'QUEUED'
    SENT = 'SENT'
    ACKED = 'ACKED'
    FAILED = 'FAILED'

