from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db import transaction

from .models import (
    Task, MotorControl, User, Motor, Spinning, ExperimentProcess,
    MaterialType, MaterialRecipe, RecipeStep, BatchJob, BatchStepExecution, CommandOutbox
)
from .serializer import TaskSerializer, MotorControlSerializer, UserSerializer, LoginRecordSerializer, \
    SpinningSerializer, ExperimentProcessSerializer, MaterialTypeSerializer, MaterialRecipeSerializer, \
    RecipeStepSerializer, BatchJobSerializer, BatchStepExecutionSerializer, CommandOutboxSerializer, \
    TopicPublishRequestSerializer, ServiceCallRequestSerializer, ActionGoalRequestSerializer
from django.contrib.auth.hashers import make_password, check_password
from django.http import JsonResponse
from datetime import datetime
from django.utils import timezone

from .token import create_token, check_token, token_auth

from .mqtt import publish_device_command, mqtt_client_available

import requests
import base64
from decimal import Decimal


@api_view(['GET', 'POST'])
def task_list(request):
    if request.method == 'GET':
        tasks = Task.objects.all()
        serializer = TaskSerializer(tasks, many=True)
        return Response(serializer.data)


@api_view(['GET', 'POST'])
def motor_control_list(request):
    if request.method == 'POST':
        serializer = MotorControlSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    elif request.method == 'GET':
        controls = MotorControl.objects.all()
        serializer = MotorControlSerializer(controls, many=True)
        return Response(serializer.data)


@api_view(['POST'])
def login(request):
    user = User.objects.filter(email=request.data['email'])
    if user:
        encoded = user[0].password
        if check_password(request.data['password'], encoded):
            token = create_token(request.data['email'])
            login_record_s = LoginRecordSerializer(data={'email': request.data['email'], 'token': token})
            if login_record_s.is_valid():
                login_record_s.save()
            else:
                print(login_record_s.errors)
            return Response({'Login Success': 'Login Success', 'token': token}, status=status.HTTP_200_OK)
        else:
            return Response({'Login Failed': 'Wrong Password!'}, status=status.HTTP_401_UNAUTHORIZED)
    else:
        return Response({'Login Failed': 'User Does Not Exist!'}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
def sign_up(request):
    data = request.data
    # Encript the password using hashing
    data['password'] = make_password(data['password'])
    serializer = UserSerializer(data=data)
    if User.objects.filter(email=data['email']).exists():
        return Response({'Registration Failed': 'User Already Exists!'}, status=status.HTTP_400_BAD_REQUEST)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def token_validation(request):
    result = check_token(request.data['token'])
    if result == 'expired':
        return Response({'Token validation': 'Expired'}, status=status.HTTP_403_FORBIDDEN)
    elif result == 'fail':
        return Response({'Token validation': 'Failed'}, status=status.HTTP_403_FORBIDDEN)
    else:
        return Response({'Token validation': 'Success', 'email': result['email']}, status=status.HTTP_200_OK)


@api_view(['POST'])
def get_user_data(request):
    if (request.data['token']):
        if token_auth(request.data['token']):
            data = User.objects.filter(email=request.data['email']).values()[0]
            del data['password']
            del data['id']
            return JsonResponse(data=data, status=status.HTTP_200_OK)


@api_view(['POST'])
def change_password(request):
    if token_auth(request.data['token']):
        user = User.objects.filter(email=request.data['email'])[0]
        if user:
            encoded = user.password
            if check_password(request.data['old_password'], encoded):
                new_password = make_password(request.data['new_password'])
                user.password = new_password
                user.save()
                return Response(status=status.HTTP_200_OK)
            else:
                return Response({'Password change fail': 'Old password wrong'}, status=status.HTTP_401_UNAUTHORIZED)
    return Response(status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
def get_motors(request):
    if token_auth(request.data['token']):
        motors = []
        for motor in Motor.objects.all().values():
            motors.append(motor)
        return Response({'motor_list': motors}, status.HTTP_200_OK)
    return Response(status=status.HTTP_403_FORBIDDEN)


@api_view(['POST'])
def spinning(request):
    if token_auth(request.data['token']):
        if request.data['data']:
            spin_instance = request.data['data']
            print(spin_instance)
            if spin_instance['motor_name']:
                spin_instance['scheduled_time'] = datetime.strptime(spin_instance['scheduled_time'],
                                                                    '%Y-%m-%dT%H:%M:%S')
                # print(spin_instance)
                spin_ser = SpinningSerializer(data=spin_instance)
                if spin_ser.is_valid():
                    spin_ser.save()
                    return Response(status.HTTP_200_OK)
            return Response(status.HTTP_400_BAD_REQUEST)
        else:
            records = []
            for record in Spinning.objects.all().values():
                records.append(record)
                record['scheduled_time'] = timezone.localtime(record['scheduled_time'])
                # print(record)
            return Response({'record_list': records}, status.HTTP_200_OK)


@api_view(['GET', 'POST'])
def test(request):
    records = []
    for record in Spinning.objects.all().values():
        temp = {
            'id': record['id'],
            'time': timezone.localtime(record['scheduled_time']).timestamp(),
            'speed': record['motor_speed'],
            'duration': record['duration_sec']
        }
        records.append(temp)
    return Response({'now': timezone.localtime().timestamp(), 'data': records}, status=status.HTTP_200_OK)


# MQTT View
@api_view(['GET', 'POST'])
def mqtt_msg(request):
    if request.method == 'POST':
        if (request.data['topic']):
            topic = request.data['topic']
            msg = request.data['msg'] * 6
            msg = 'pwm_' + str(msg)
            # return Response(status=status.HTTP_200_OK)
            rc, mid = mqtt_client.publish(topic, msg)
            return JsonResponse({'code': rc})
        else:
            return Response({'request fail': 'Deined'}, status=status.HTTP_403_FORBIDDEN)
    if request.method == 'GET':
        motor_speed = MotorControl.objects.values().last()['motor_speed']
        return Response({'speed': motor_speed}, status=status.HTTP_200_OK)


# Device List
@api_view(['GET'])
def device_list(request):
    # 限制只接受一页，并且每页上限50个设备
    url = "http://localhost:18083/api/v5/clients?page=1&limit=50&node=emqx%40127.0.0.1"
    # EMQX 的密钥信息
    api_key = "14d39e44d739b1d9"
    secret_key = "DrXETy29CGKJnUHWMTQauKnOYzBN9A65z5Yw4FiUMpt9BC"

    # 使用Base64方式加密密钥对
    credentials = f"{api_key}:{secret_key}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Basic ' + encoded_credentials
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # 如果响应码不是200，会抛出异常

        # 获取连接信息
        connections = response.json()
        return JsonResponse(connections, safe=False)
    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['GET', 'POST'])
def experiment_process_list(request):
    if request.method == 'GET':
        records = ExperimentProcess.objects.all().order_by('-created_at')
        serializer = ExperimentProcessSerializer(records, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    serializer = ExperimentProcessSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
def experiment_process_detail(request, experiment_id):
    try:
        record = ExperimentProcess.objects.get(experiment_id=experiment_id)
    except ExperimentProcess.DoesNotExist:
        return Response({'detail': 'Experiment not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        serializer = ExperimentProcessSerializer(record)
        return Response(serializer.data, status=status.HTTP_200_OK)

    if request.method == 'DELETE':
        record.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    partial = request.method == 'PATCH'
    serializer = ExperimentProcessSerializer(record, data=request.data, partial=partial)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'POST'])
def material_type_list(request):
    if request.method == 'GET':
        records = MaterialType.objects.all().order_by('name')
        serializer = MaterialTypeSerializer(records, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    serializer = MaterialTypeSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'POST'])
def material_recipe_list(request):
    if request.method == 'GET':
        records = MaterialRecipe.objects.all().order_by('-updated_at')
        serializer = MaterialRecipeSerializer(records, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    serializer = MaterialRecipeSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
def material_recipe_detail(request, recipe_id):
    try:
        record = MaterialRecipe.objects.get(id=recipe_id)
    except MaterialRecipe.DoesNotExist:
        return Response({'detail': 'Recipe not found.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = MaterialRecipeSerializer(record)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
def recipe_step_list_create(request, recipe_id):
    try:
        recipe = MaterialRecipe.objects.get(id=recipe_id)
    except MaterialRecipe.DoesNotExist:
        return Response({'detail': 'Recipe not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        steps = RecipeStep.objects.filter(recipe=recipe).order_by('step_no', 'id')
        serializer = RecipeStepSerializer(steps, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    data = request.data.copy()
    data['recipe'] = recipe.id
    serializer = RecipeStepSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


def _build_planned_parameters(recipe, overrides):
    def _jsonable(value):
        if isinstance(value, Decimal):
            return float(value)
        return value

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


def _build_step_command_payload(recipe_step, planned_parameters):
    interface_type, route_name = _resolve_step_interface(recipe_step.step_type, recipe_step.parameters or {})
    payload = {
        'step_no': recipe_step.step_no,
        'step_type': recipe_step.step_type,
        'name': recipe_step.name or f'Step {recipe_step.step_no}',
        'interface_type': interface_type,
        'route_name': route_name,
        'parameters': recipe_step.parameters or {},
        'planned_parameters': planned_parameters,
    }
    return payload


def _coerce_positive_int(value, default=None):
    if value is None or value == '':
        return default
    return max(int(float(value)), 0)


def _resolve_motor_command(step_execution):
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

    motor = _coerce_positive_int(motor, 0)
    speed = _coerce_positive_int(speed)
    duration = _coerce_positive_int(duration)
    if speed is None or duration is None:
        raise ValueError('Motor step is missing speed or duration.')

    topic = parameters.get('topic', 'esp32_1/control')
    raw_payload = f'cmd_{motor}_{speed}_{duration}'

    return {
        'topic': topic,
        'payload': raw_payload,
        'transport': 'mqtt',
        'device': parameters.get('device', 'esp32'),
        'command_type': 'motor_cmd',
        'interface_type': 'topic',
        'route_name': topic,
    }


def _resolve_generic_command(step_execution):
    payload = step_execution.command_payload or {}
    parameters = payload.get('parameters') or {}
    topic = parameters.get('topic')
    if not topic:
        raise ValueError('Step parameters must define a topic for generic dispatch.')

    generic_payload = {
        'job_id': step_execution.job_id,
        'step_execution_id': step_execution.id,
        'step_no': payload.get('step_no'),
        'step_type': payload.get('step_type'),
        'name': payload.get('name'),
        'parameters': parameters,
        'planned_parameters': payload.get('planned_parameters') or {}
    }
    return {
        'topic': topic,
        'payload': generic_payload,
        'transport': 'mqtt',
        'device': parameters.get('device', 'generic'),
        'command_type': 'generic_json',
        'interface_type': payload.get('interface_type', 'topic'),
        'route_name': payload.get('route_name') or topic,
    }


def _resolve_step_interface(step_type, parameters):
    explicit_interface = parameters.get('interface_type')
    if explicit_interface:
        route_name = parameters.get('route_name') or parameters.get('service_name') or parameters.get('action_name') or parameters.get('topic')
        return explicit_interface, route_name

    if step_type in ['STIR', 'DISPENSE']:
        return 'topic', parameters.get('topic', 'esp32_1/control')
    if step_type in ['MOVE_ARM', 'HEAT', 'CLEAN']:
        return 'action', parameters.get('action_name') or parameters.get('topic')
    if step_type in ['WAIT', 'SAMPLE']:
        return 'service', parameters.get('service_name') or parameters.get('topic')
    return 'topic', parameters.get('topic')


def _resolve_dispatch_command(step_execution):
    payload = step_execution.command_payload or {}
    step_type = payload.get('step_type')
    interface_type = payload.get('interface_type')
    if step_type in ['STIR', 'DISPENSE']:
        return _resolve_motor_command(step_execution)
    if interface_type in ['topic', 'service', 'action']:
        return _resolve_generic_command(step_execution)
    return _resolve_generic_command(step_execution)


def _resolve_outbox_context(job_id=None, step_execution_id=None):
    job = None
    step_execution = None

    if step_execution_id is not None:
        try:
            step_execution = BatchStepExecution.objects.get(id=step_execution_id)
        except BatchStepExecution.DoesNotExist:
            raise ValueError('Step execution not found.')
        job = step_execution.job

    if job_id is not None:
        try:
            requested_job = BatchJob.objects.get(id=job_id)
        except BatchJob.DoesNotExist:
            raise ValueError('Job not found.')
        if job is not None and job.id != requested_job.id:
            raise ValueError('step_execution_id does not belong to job_id.')
        job = requested_job

    return job, step_execution


def _queue_transport_message(*, topic, payload, interface_type, route_name, job=None, step_execution=None, device=None):
    outbox = CommandOutbox.objects.create(
        job=job,
        step_execution=step_execution,
        topic=topic,
        payload={
            'interface_type': interface_type,
            'route_name': route_name,
            'device': device,
            'body': payload,
        },
        status='QUEUED',
    )

    dispatch_error = None
    if mqtt_client_available():
        try:
            publish_device_command(topic, payload)
            outbox.status = 'SENT'
            outbox.sent_at = timezone.now()
            outbox.save(update_fields=['status', 'sent_at', 'updated_at'])
        except Exception as exc:
            dispatch_error = str(exc)
            outbox.status = 'FAILED'
            outbox.error_message = dispatch_error
            outbox.save(update_fields=['status', 'error_message', 'updated_at'])
    else:
        dispatch_error = 'MQTT client unavailable.'

    return outbox, dispatch_error


@api_view(['POST'])
def communication_topic_publish(request):
    serializer = TopicPublishRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    try:
        job, step_execution = _resolve_outbox_context(
            job_id=data.get('job_id'),
            step_execution_id=data.get('step_execution_id'),
        )
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    outbox, dispatch_error = _queue_transport_message(
        topic=data['topic'],
        payload=data['payload'],
        interface_type='topic',
        route_name=data['topic'],
        job=job,
        step_execution=step_execution,
        device=data.get('device'),
    )

    return Response({
        'interface_type': 'topic',
        'outbox_message': CommandOutboxSerializer(outbox).data,
        'mqtt_available': mqtt_client_available(),
        'dispatched': outbox.status == 'SENT',
        'detail': dispatch_error or 'Topic message published successfully.',
    }, status=status.HTTP_200_OK if outbox.status == 'SENT' else status.HTTP_202_ACCEPTED)


@api_view(['POST'])
def communication_service_call(request):
    serializer = ServiceCallRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    try:
        job, step_execution = _resolve_outbox_context(
            job_id=data.get('job_id'),
            step_execution_id=data.get('step_execution_id'),
        )
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    payload = {
        'service_name': data['service_name'],
        'request': data['request'],
        'timeout_sec': data.get('timeout_sec', 10),
    }
    outbox, dispatch_error = _queue_transport_message(
        topic=data['topic'],
        payload=payload,
        interface_type='service',
        route_name=data['service_name'],
        job=job,
        step_execution=step_execution,
        device=data.get('device'),
    )

    return Response({
        'interface_type': 'service',
        'service_name': data['service_name'],
        'outbox_message': CommandOutboxSerializer(outbox).data,
        'mqtt_available': mqtt_client_available(),
        'dispatched': outbox.status == 'SENT',
        'detail': dispatch_error or 'Service request dispatched. Await device response asynchronously.',
    }, status=status.HTTP_200_OK if outbox.status == 'SENT' else status.HTTP_202_ACCEPTED)


@api_view(['POST'])
def communication_action_goal(request):
    serializer = ActionGoalRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    data = serializer.validated_data
    try:
        job, step_execution = _resolve_outbox_context(
            job_id=data.get('job_id'),
            step_execution_id=data.get('step_execution_id'),
        )
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    payload = {
        'action_name': data['action_name'],
        'goal': data['goal'],
        'expected_duration_sec': data.get('expected_duration_sec'),
    }
    outbox, dispatch_error = _queue_transport_message(
        topic=data['topic'],
        payload=payload,
        interface_type='action',
        route_name=data['action_name'],
        job=job,
        step_execution=step_execution,
        device=data.get('device'),
    )

    return Response({
        'interface_type': 'action',
        'action_name': data['action_name'],
        'outbox_message': CommandOutboxSerializer(outbox).data,
        'mqtt_available': mqtt_client_available(),
        'dispatched': outbox.status == 'SENT',
        'detail': dispatch_error or 'Action goal dispatched. Track progress through job status or telemetry.',
    }, status=status.HTTP_200_OK if outbox.status == 'SENT' else status.HTTP_202_ACCEPTED)


@api_view(['POST'])
def batch_job_create(request):
    recipe_id = request.data.get('recipe_id')
    if not recipe_id:
        return Response({'recipe_id': ['This field is required.']}, status=status.HTTP_400_BAD_REQUEST)

    try:
        recipe = MaterialRecipe.objects.get(id=recipe_id)
    except MaterialRecipe.DoesNotExist:
        return Response({'detail': 'Recipe not found.'}, status=status.HTTP_404_NOT_FOUND)

    overrides = request.data.get('overrides') or {}
    if not isinstance(overrides, dict):
        return Response({'overrides': ['Must be a JSON object.']}, status=status.HTTP_400_BAD_REQUEST)

    operator = request.data.get('operator')
    planned_parameters = _build_planned_parameters(recipe, overrides)
    recipe_steps = list(RecipeStep.objects.filter(recipe=recipe).order_by('step_no', 'id'))
    if not recipe_steps:
        return Response({'detail': 'Recipe has no steps configured.'}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        job = BatchJob.objects.create(
            recipe=recipe,
            status='PENDING',
            operator=operator,
            planned_parameters=planned_parameters,
            overrides=overrides,
        )

        execution_records = []
        for step in recipe_steps:
            payload = _build_step_command_payload(step, planned_parameters)
            execution_records.append(
                BatchStepExecution(
                    job=job,
                    recipe_step=step,
                    status='PENDING',
                    command_payload=payload,
                )
            )
        BatchStepExecution.objects.bulk_create(execution_records)

    serializer = BatchJobSerializer(job)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
def batch_job_start(request, job_id):
    try:
        job = BatchJob.objects.get(id=job_id)
    except BatchJob.DoesNotExist:
        return Response({'detail': 'Job not found.'}, status=status.HTTP_404_NOT_FOUND)

    if job.status not in ['PENDING', 'PAUSED']:
        return Response({'detail': f'Job cannot be started from status {job.status}.'}, status=status.HTTP_400_BAD_REQUEST)

    dispatched_messages = []
    failed_steps = []

    with transaction.atomic():
        now = timezone.now()
        if not job.started_at:
            job.started_at = now
        job.status = 'RUNNING'
        job.error_message = None
        job.save(update_fields=['status', 'error_message', 'started_at', 'updated_at'])

        pending_steps = BatchStepExecution.objects.filter(job=job, status='PENDING').order_by('id')
        for step_execution in pending_steps:
            try:
                dispatch = _resolve_dispatch_command(step_execution)
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
                    status='QUEUED',
                )
                publish_device_command(dispatch['topic'], dispatch['payload'])
                outbox.status = 'SENT'
                outbox.sent_at = timezone.now()
                outbox.save(update_fields=['status', 'sent_at', 'updated_at'])

                step_execution.status = 'RUNNING'
                step_execution.started_at = timezone.now()
                step_execution.telemetry = {
                    **(step_execution.telemetry or {}),
                    'dispatch_topic': dispatch['topic'],
                    'dispatch_payload': dispatch['payload'],
                    'dispatch_transport': dispatch['transport'],
                    'dispatch_interface_type': dispatch.get('interface_type'),
                    'dispatch_route_name': dispatch.get('route_name'),
                }
                step_execution.save(update_fields=['status', 'started_at', 'telemetry', 'updated_at'])
                dispatched_messages.append(outbox)
            except Exception as exc:
                step_execution.status = 'FAILED'
                step_execution.error_message = str(exc)
                step_execution.save(update_fields=['status', 'error_message', 'updated_at'])
                failed_steps.append({
                    'step_execution_id': step_execution.id,
                    'step_no': step_execution.command_payload.get('step_no'),
                    'error': str(exc),
                })

        if failed_steps and not dispatched_messages:
            job.status = 'FAILED'
            job.error_message = 'Unable to dispatch any device commands.'
            job.finished_at = timezone.now()
            job.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])

    return Response({
        'job_id': job.id,
        'status': job.status,
        'mqtt_available': mqtt_client_available(),
        'dispatched_messages': CommandOutboxSerializer(dispatched_messages, many=True).data,
        'failed_steps': failed_steps,
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
def batch_job_status(request, job_id):
    try:
        job = BatchJob.objects.get(id=job_id)
    except BatchJob.DoesNotExist:
        return Response({'detail': 'Job not found.'}, status=status.HTTP_404_NOT_FOUND)

    step_qs = BatchStepExecution.objects.filter(job=job)
    step_status_counts = {
        'pending': step_qs.filter(status='PENDING').count(),
        'queued': step_qs.filter(status='QUEUED').count(),
        'running': step_qs.filter(status='RUNNING').count(),
        'done': step_qs.filter(status='DONE').count(),
        'failed': step_qs.filter(status='FAILED').count(),
        'skipped': step_qs.filter(status='SKIPPED').count(),
    }
    next_step = step_qs.filter(status__in=['PENDING', 'QUEUED', 'RUNNING']).order_by('id').first()
    next_step_data = None
    if next_step:
        next_step_data = BatchStepExecutionSerializer(next_step).data

    outbox_messages = CommandOutbox.objects.filter(job=job).order_by('-created_at')

    return Response({
        'job': BatchJobSerializer(job).data,
        'step_status_counts': step_status_counts,
        'next_step': next_step_data,
        'step_executions': BatchStepExecutionSerializer(step_qs, many=True).data,
        'outbox_messages': CommandOutboxSerializer(outbox_messages, many=True).data,
    }, status=status.HTTP_200_OK)
