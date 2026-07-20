from rest_framework import serializers
from .models import (
    Task, MotorControl, User, LoginRecord, Motor, Spinning, MotorEvent, MotorData, ExperimentProcess,
    MaterialType, MaterialRecipe, RecipeStep, BatchJob, BatchStepExecution, CommandOutbox, TelemetryIngest,
    Device, EmergencyStopLog
)

class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = '__all__'
        read_only_fields = ('task_id',)

class MotorControlSerializer(serializers.ModelSerializer):
    class Meta:
        model = MotorControl
        fields = '__all__'
        read_only_fields = ('id',)

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'

class LoginRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoginRecord
        fields = '__all__'

class MotorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Motor
        fields = '__all__'

class SpinningSerializer(serializers.ModelSerializer):
    class Meta:
        model = Spinning
        fields = '__all__'

class MotorEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = MotorEvent
        fields = '__all__'

class MotorDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = MotorData
        fields = '__all__'


class ExperimentProcessSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExperimentProcess
        fields = '__all__'


class MaterialTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaterialType
        fields = '__all__'


class MaterialRecipeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MaterialRecipe
        fields = '__all__'


class RecipeStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecipeStep
        fields = '__all__'


class BatchJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchJob
        fields = '__all__'


class BatchStepExecutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BatchStepExecution
        fields = '__all__'


class CommandOutboxSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommandOutbox
        fields = '__all__'


class TelemetryIngestSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelemetryIngest
        fields = '__all__'


class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class EmergencyStopLogSerializer(serializers.ModelSerializer):
    device_label = serializers.CharField(source='device.label', read_only=True)
    device_id = serializers.CharField(source='device.device_id', read_only=True)

    class Meta:
        model = EmergencyStopLog
        fields = '__all__'
        read_only_fields = ('triggered_at',)


class TopicPublishRequestSerializer(serializers.Serializer):
    topic = serializers.CharField(max_length=128)
    payload = serializers.JSONField()
    job_id = serializers.IntegerField(required=False)
    step_execution_id = serializers.IntegerField(required=False)
    transport = serializers.ChoiceField(choices=['mqtt', 'ros2'], required=False, default='mqtt')
    device = serializers.JSONField(required=False)


class ServiceCallRequestSerializer(serializers.Serializer):
    service_name = serializers.CharField(max_length=128)
    topic = serializers.CharField(max_length=128)
    request = serializers.JSONField()
    job_id = serializers.IntegerField(required=False)
    step_execution_id = serializers.IntegerField(required=False)
    timeout_sec = serializers.IntegerField(required=False, min_value=1)
    transport = serializers.ChoiceField(choices=['mqtt', 'ros2'], required=False, default='mqtt')
    device = serializers.JSONField(required=False)


class ActionGoalRequestSerializer(serializers.Serializer):
    action_name = serializers.CharField(max_length=128)
    topic = serializers.CharField(max_length=128)
    goal = serializers.JSONField()
    job_id = serializers.IntegerField(required=False)
    step_execution_id = serializers.IntegerField(required=False)
    expected_duration_sec = serializers.IntegerField(required=False, min_value=1)
    transport = serializers.ChoiceField(choices=['mqtt', 'ros2'], required=False, default='mqtt')
    device = serializers.JSONField(required=False)
