from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class StepDispatch:
    topic: str
    payload: object
    transport: str
    device: object
    command_type: str
    interface_type: str
    route_name: str


def _jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def build_planned_parameters(recipe, overrides):
    planned = {
        'dmac_dosage_ml': _jsonable(recipe.dmac_dosage_ml),
        'water_dosage_ml': _jsonable(recipe.water_dosage_ml),
        'solvent_ph': _jsonable(recipe.solvent_ph),
        'reaction_temperature_c': _jsonable(recipe.reaction_temperature_c),
        'stirring_speed_rpm': _jsonable(recipe.stirring_speed_rpm),
        'stirring_duration_min': _jsonable(recipe.stirring_duration_min),
    }
    for key, value in (overrides or {}).items():
        if key in planned:
            planned[key] = _jsonable(value)
    return planned


def coerce_positive_int(value, default=None):
    if value is None or value == '':
        return default
    return max(int(float(value)), 0)


def normalize_device_descriptor(parameters):
    device = parameters.get('device')
    if isinstance(device, dict):
        return device
    device_id = parameters.get('device_id') or ''
    if device:
        return {'type': str(device), 'id': device_id}
    return {'type': 'generic', 'id': device_id}


class StepExecutor:
    supported_step_types = ()

    def build_command_payload(self, recipe_step, planned_parameters, *, default_device_id):
        parameters = recipe_step.parameters or {}
        interface_type, route_name = self.resolve_interface(parameters, default_device_id=default_device_id)
        transport = self.resolve_transport(parameters)
        return {
            'step_no': recipe_step.step_no,
            'step_type': recipe_step.step_type,
            'transport': transport,
            'name': recipe_step.name or f'Step {recipe_step.step_no}',
            'interface_type': interface_type,
            'route_name': route_name,
            'parameters': parameters,
            'planned_parameters': planned_parameters,
        }

    def resolve_interface(self, parameters, *, default_device_id):
        explicit_interface = parameters.get('interface_type')
        if explicit_interface:
            route_name = (
                parameters.get('route_name')
                or parameters.get('service_name')
                or parameters.get('action_name')
                or parameters.get('topic')
            )
            return explicit_interface, route_name
        raise NotImplementedError

    def resolve_transport(self, parameters):
        explicit_transport = parameters.get('transport')
        if explicit_transport:
            return explicit_transport
        return 'mqtt'

    def resolve_dispatch(self, step_execution, *, default_control_topic):
        raise NotImplementedError


class MotorStepExecutor(StepExecutor):
    supported_step_types = ('STIR', 'DISPENSE')

    def resolve_interface(self, parameters, *, default_device_id):
        return 'topic', parameters.get('topic', default_control_topic_for_device(default_device_id))

    def resolve_dispatch(self, step_execution, *, default_control_topic):
        payload = step_execution.command_payload or {}
        parameters = payload.get('parameters') or {}
        planned = payload.get('planned_parameters') or {}

        motor = parameters.get('motor')
        if motor is None:
            motor = parameters.get('motor_index', 0)

        speed = parameters.get('speed')
        if speed is None and parameters.get('speed_key'):
            speed = planned.get(parameters.get('speed_key'))
        if speed is None:
            speed = planned.get('stirring_speed_rpm')

        duration = parameters.get('duration_sec')
        if duration is None and parameters.get('duration_key'):
            duration = planned.get(parameters.get('duration_key'))
        if duration is None:
            duration_min = planned.get('stirring_duration_min')
            if duration_min is not None:
                duration = float(duration_min) * 60

        motor = coerce_positive_int(motor, 0)
        speed = coerce_positive_int(speed)
        duration = coerce_positive_int(duration)
        if speed is None or duration is None:
            raise ValueError('Motor step is missing speed or duration.')

        topic = parameters.get('topic', default_control_topic)
        raw_payload = f'cmd_{motor}_{speed}_{duration}'
        return StepDispatch(
            topic=topic,
            payload=raw_payload,
            transport='mqtt',
            device=parameters.get('device', 'esp32'),
            command_type='motor_cmd',
            interface_type='topic',
            route_name=topic,
        )


class MoveArmStepExecutor(StepExecutor):
    supported_step_types = ('MOVE_ARM',)

    def resolve_interface(self, parameters, *, default_device_id):
        return 'action', parameters.get('action_name') or parameters.get('topic')

    def resolve_transport(self, parameters):
        explicit_transport = parameters.get('transport')
        if explicit_transport:
            return explicit_transport
        return 'ros2'

    def resolve_dispatch(self, step_execution, *, default_control_topic):
        return build_generic_dispatch(step_execution)


class WaitStepExecutor(StepExecutor):
    supported_step_types = ('WAIT',)

    def resolve_interface(self, parameters, *, default_device_id):
        return 'service', parameters.get('service_name') or parameters.get('topic')

    def resolve_dispatch(self, step_execution, *, default_control_topic):
        return build_generic_dispatch(step_execution)


class GenericStepExecutor(StepExecutor):
    supported_step_types = ()

    def resolve_interface(self, parameters, *, default_device_id):
        explicit_interface = parameters.get('interface_type')
        if explicit_interface:
            route_name = (
                parameters.get('route_name')
                or parameters.get('service_name')
                or parameters.get('action_name')
                or parameters.get('topic')
            )
            return explicit_interface, route_name
        return 'topic', parameters.get('topic')

    def resolve_dispatch(self, step_execution, *, default_control_topic):
        return build_generic_dispatch(step_execution)


def build_generic_dispatch(step_execution):
    payload = step_execution.command_payload or {}
    parameters = payload.get('parameters') or {}
    transport = payload.get('transport') or 'mqtt'
    topic = parameters.get('topic')
    route_name = payload.get('route_name') or topic
    if transport == 'mqtt' and not topic:
        raise ValueError('Step parameters must define a topic for mqtt dispatch.')
    if transport == 'ros2' and not route_name:
        raise ValueError('ROS2 step must define route_name/action_name/service_name.')

    if transport == 'ros2':
        interface_type = payload.get('interface_type', 'action')
        if interface_type == 'action':
            generic_payload = {
                'action_name': parameters.get('action_name') or route_name,
                'goal': parameters.get('goal') or {
                    'trajectory': parameters.get('trajectory') or parameters.get('waypoints') or [],
                    'pose': parameters.get('pose'),
                },
                'expected_duration_sec': parameters.get('expected_duration_sec'),
            }
        elif interface_type == 'service':
            generic_payload = {
                'service_name': parameters.get('service_name') or route_name,
                'request': parameters.get('request') or {},
                'timeout_sec': parameters.get('timeout_sec', 10),
            }
        else:
            generic_payload = {
                'topic_name': parameters.get('topic_name') or route_name,
                'message': parameters.get('message') or {},
            }
    else:
        generic_payload = {
            'job_id': step_execution.job_id,
            'step_execution_id': step_execution.id,
            'step_no': payload.get('step_no'),
            'step_type': payload.get('step_type'),
            'name': payload.get('name'),
            'parameters': parameters,
            'planned_parameters': payload.get('planned_parameters') or {},
        }

    return StepDispatch(
        topic=topic or route_name,
        payload=generic_payload,
        transport=transport,
        device=normalize_device_descriptor(parameters),
        command_type='generic_json',
        interface_type=payload.get('interface_type', 'topic'),
        route_name=route_name,
    )


def default_control_topic_for_device(default_device_id):
    return f'{default_device_id}/control' if '/' not in default_device_id else default_device_id


class StepExecutorRegistry:
    def __init__(self, executors=None, fallback=None):
        self._executors = {}
        for executor in executors or []:
            for step_type in executor.supported_step_types:
                self._executors[step_type] = executor
        self._fallback = fallback or GenericStepExecutor()

    def get(self, step_type):
        return self._executors.get(step_type, self._fallback)

    def build_command_payload(self, recipe_step, planned_parameters, *, default_device_id):
        executor = self.get(recipe_step.step_type)
        return executor.build_command_payload(recipe_step, planned_parameters, default_device_id=default_device_id)

    def resolve_dispatch(self, step_execution, *, default_control_topic):
        step_type = (step_execution.command_payload or {}).get('step_type')
        executor = self.get(step_type)
        dispatch = executor.resolve_dispatch(step_execution, default_control_topic=default_control_topic)
        return {
            'topic': dispatch.topic,
            'payload': dispatch.payload,
            'transport': dispatch.transport,
            'device': dispatch.device,
            'command_type': dispatch.command_type,
            'interface_type': dispatch.interface_type,
            'route_name': dispatch.route_name,
        }


default_step_executor_registry = StepExecutorRegistry(
    executors=[
        MotorStepExecutor(),
        MoveArmStepExecutor(),
        WaitStepExecutor(),
    ],
)
