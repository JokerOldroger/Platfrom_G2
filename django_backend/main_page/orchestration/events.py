from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceReplyEvent:
    interface_type: str
    message_type: str
    status: str | None
    error_message: str | None = None

