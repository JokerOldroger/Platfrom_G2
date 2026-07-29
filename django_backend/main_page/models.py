from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.conf import settings

# Create your models here.

class Task(models.Model):
    task_id = models.AutoField(primary_key=True, null=False)
    task_name = models.CharField(max_length=128, null=False)
    task_description = models.CharField(max_length=256)

class MotorControl(models.Model):
    id = models.AutoField(primary_key=True, null=False)
    motor_name = models.CharField(max_length=128, null=False)
    motor_speed = models.IntegerField(null=False)
    time = models.DateTimeField(auto_now_add=True, null=False)

class User(models.Model):
    id = models.AutoField(primary_key=True, null=False)
    email = models.CharField(max_length=128, null=False)
    username = models.CharField(max_length=128, null=False)
    password = models.CharField(max_length=256)
    activated = models.BooleanField(default=False)
    register_time = models.DateTimeField(auto_now_add=True, null=False)

class LoginRecord(models.Model):
    id = models.AutoField(primary_key=True, null=False)
    email = models.CharField(max_length=128, null=False)
    login_time = models.DateTimeField(auto_now_add=True, null=False)
    token = models.CharField(max_length=512, null=False)

class Motor(models.Model):
    id = models.AutoField(primary_key=True, null=False)
    name = models.CharField(max_length=64, null=False)
    motor_index = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(3)],
        help_text='对应 ESP32 的电机索引 0-3'
    )
    avaliable = models.BooleanField(default=True)
    description = models.CharField(max_length=256)

EVENT_STATUS = (
    (1, 'Active'),
    (2, 'Done')
)
DEFAULT_EVENT_STATUS = 1

class MotorEvent(models.Model):
    id = models.AutoField(primary_key=True, null=False)
    timestamp = models.DateTimeField(auto_now_add=True, null=False)
    device_id = models.CharField(
        max_length=32,
        default=getattr(settings, 'MQTT_DEFAULT_DEVICE_ID', 'esp32_1'),
        help_text='ESP32 设备逻辑标识，如 esp32_7cdfa1e6d3cc',
    )
    motor = models.IntegerField(null=False)
    speed = models.IntegerField(null=False)
    time  = models.IntegerField(null=False)
    statue = models.IntegerField(choices=EVENT_STATUS, default=DEFAULT_EVENT_STATUS)


MOTOR_CHOICES = (
    (0, 'Motor_0'),
    (1, 'Motor_1'),
    (2, 'Motor_2'),
    (3, 'Motor_3'),
)
DEFAULT_MOTOR = 0
MOTOR_DATA_TYPE = (
    (1, 'PCNT'),
    (2, 'PWM')
)
DEFAULT_MOTOR_DATA = 1

class MotorData(models.Model):
    id = models.AutoField(primary_key=True, null=False)
    timestamp = models.DateTimeField(auto_now_add=True, null=False)
    parent_event_id = models.ForeignKey(MotorEvent, on_delete=models.CASCADE)
    motor_id = models.IntegerField(choices=MOTOR_CHOICES, default=DEFAULT_MOTOR)
    data_type = models.IntegerField(choices=MOTOR_DATA_TYPE, default=DEFAULT_MOTOR_DATA)
    data = models.IntegerField(null=False)


SPINNING_STATUS_CHOICES = (
    ('PENDING', 'Pending'),
    ('SENT', 'Sent'),
    ('RUNNING', 'Running'),
    ('FINISHED', 'Finished'),
    ('FAILED', 'Failed'),
    ('COMPLETED', 'Completed'),
    ('CANCELLED', 'Cancelled'),
)
DEFAULT_SPINNING_STATUS = 'PENDING'


class Spinning(models.Model):
    id = models.AutoField(primary_key=True, null=False)
    motor_name = models.CharField(max_length=128, null=False)
    motor_names = models.JSONField(
        default=list,
        blank=True,
        help_text='多电机调度时存储选中的电机名称列表',
    )
    scheduled_time = models.DateTimeField(null=False)
    motor_speed = models.IntegerField(null=False)
    duration_sec = models.IntegerField(null=False)
    status = models.CharField(
        max_length=16,
        choices=SPINNING_STATUS_CHOICES,
        default=DEFAULT_SPINNING_STATUS,
        db_index=True,
    )
    device_id = models.CharField(
        max_length=32,
        default=getattr(settings, 'MQTT_DEFAULT_DEVICE_ID', 'esp32_1'),
        help_text='目标设备逻辑标识，如 esp32_1',
    )
    dispatched_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.CharField(max_length=256, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    def effective_motor_names(self):
        """返回有效的电机名称列表；兼容旧版单电机记录。"""
        if self.motor_names:
            return list(self.motor_names)
        return [self.motor_name] if self.motor_name else []

# class UpdateRecord(models.Model):
#     id = models.AutoField(primary_key=True, null=False)
#     time = models.DateTimeField(auto_now_add=True, null=False)
#     valid = models.BooleanField(default=False)


class ExperimentProcess(models.Model):
    experiment_id = models.CharField(max_length=50, primary_key=True, null=False)
    experiment_name = models.CharField(max_length=100, null=False)
    zinc_acetate_dosage_g = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    dmac_dosage_ml = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    water_type = models.CharField(max_length=50, null=True, blank=True)
    water_dosage_ml = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    heating_method = models.CharField(max_length=50, null=True, blank=True)
    ph_adjust_config = models.CharField(max_length=100, null=True, blank=True)
    solvent_ph = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    precursor_volume_ml = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    container_volume_ml = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    cleaning_solution_type = models.CharField(max_length=50, null=True, blank=True)
    cleaning_solution_volume_ml = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    reaction_temperature_c = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    stirring_speed_rpm = models.IntegerField(null=True, blank=True)
    stirring_duration_min = models.IntegerField(null=True, blank=True)
    cool_down_rt_duration_min = models.IntegerField(null=True, blank=True)
    drying_temperature_c = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    drying_duration_h = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=False)
    updated_at = models.DateTimeField(auto_now=True, null=False)


class CharacterizationResult(models.Model):
    result_id = models.AutoField(primary_key=True, null=False)
    experiment = models.ForeignKey(
        ExperimentProcess,
        on_delete=models.CASCADE,
        to_field='experiment_id',
        db_column='experiment_id',
        related_name='characterization_results'
    )
    transmittance_365nm = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        null=False
    )
    transmittance_760nm = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        null=False
    )
    transmittance_970nm = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        null=False
    )
    measurement_date = models.DateField(null=True, blank=True)
    measurement_notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=False)

    class Meta:
        db_table = 'characterization_results'
        constraints = [
            models.CheckConstraint(
                check=models.Q(transmittance_365nm__gte=0) & models.Q(transmittance_365nm__lte=100),
                name='characterization_results_365nm_range'
            ),
            models.CheckConstraint(
                check=models.Q(transmittance_760nm__gte=0) & models.Q(transmittance_760nm__lte=100),
                name='characterization_results_760nm_range'
            ),
            models.CheckConstraint(
                check=models.Q(transmittance_970nm__gte=0) & models.Q(transmittance_970nm__lte=100),
                name='characterization_results_970nm_range'
            ),
        ]


STEP_TYPE_CHOICES = (
    ('DISPENSE', 'Dispense'),
    ('MOVE_ARM', 'Move Arm'),
    ('STIR', 'Stir'),
    ('HEAT', 'Heat'),
    ('WAIT', 'Wait'),
    ('SAMPLE', 'Sample'),
    ('CLEAN', 'Clean'),
)

JOB_STATUS_CHOICES = (
    ('PENDING', 'Pending'),
    ('RUNNING', 'Running'),
    ('PAUSED', 'Paused'),
    ('DONE', 'Done'),
    ('FAILED', 'Failed'),
    ('ABORTED', 'Aborted'),
)

STEP_EXEC_STATUS_CHOICES = (
    ('PENDING', 'Pending'),
    ('QUEUED', 'Queued'),
    ('RUNNING', 'Running'),
    ('DONE', 'Done'),
    ('FAILED', 'Failed'),
    ('SKIPPED', 'Skipped'),
)

OUTBOX_STATUS_CHOICES = (
    ('QUEUED', 'Queued'),
    ('SENT', 'Sent'),
    ('ACKED', 'Acked'),
    ('FAILED', 'Failed'),
)


class MaterialType(models.Model):
    id = models.AutoField(primary_key=True, null=False)
    name = models.CharField(max_length=100, unique=True, null=False)
    description = models.CharField(max_length=256, null=True, blank=True)
    is_active = models.BooleanField(default=True, null=False)
    created_at = models.DateTimeField(auto_now_add=True, null=False)
    updated_at = models.DateTimeField(auto_now=True, null=False)


class MaterialRecipe(models.Model):
    id = models.AutoField(primary_key=True, null=False)
    material_type = models.ForeignKey(MaterialType, on_delete=models.CASCADE, related_name='recipes')
    name = models.CharField(max_length=100, default='Default Recipe', null=False)
    version = models.IntegerField(default=1, null=False)
    is_active = models.BooleanField(default=True, null=False)
    notes = models.CharField(max_length=256, null=True, blank=True)

    dmac_dosage_ml = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    water_dosage_ml = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    solvent_ph = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    reaction_temperature_c = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    stirring_speed_rpm = models.IntegerField(null=True, blank=True)
    stirring_duration_min = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, null=False)
    updated_at = models.DateTimeField(auto_now=True, null=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['material_type', 'version'], name='uq_material_recipe_version'),
        ]


class RecipeStep(models.Model):
    id = models.AutoField(primary_key=True, null=False)
    recipe = models.ForeignKey(MaterialRecipe, on_delete=models.CASCADE, related_name='steps')
    step_no = models.IntegerField(null=False)
    step_type = models.CharField(max_length=20, choices=STEP_TYPE_CHOICES, null=False)
    name = models.CharField(max_length=100, null=True, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    expected_duration_sec = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=False)
    updated_at = models.DateTimeField(auto_now=True, null=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['recipe', 'step_no'], name='uq_recipe_step_no'),
        ]
        ordering = ['step_no', 'id']


class BatchJob(models.Model):
    id = models.AutoField(primary_key=True, null=False)
    recipe = models.ForeignKey(MaterialRecipe, on_delete=models.PROTECT, related_name='jobs')
    status = models.CharField(max_length=20, choices=JOB_STATUS_CHOICES, default='PENDING', null=False)
    operator = models.CharField(max_length=128, null=True, blank=True)
    planned_parameters = models.JSONField(default=dict, blank=True)
    overrides = models.JSONField(default=dict, blank=True)
    error_message = models.CharField(max_length=256, null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=False)
    updated_at = models.DateTimeField(auto_now=True, null=False)


class BatchStepExecution(models.Model):
    id = models.AutoField(primary_key=True, null=False)
    job = models.ForeignKey(BatchJob, on_delete=models.CASCADE, related_name='step_executions')
    recipe_step = models.ForeignKey(RecipeStep, on_delete=models.PROTECT, related_name='executions')
    status = models.CharField(max_length=20, choices=STEP_EXEC_STATUS_CHOICES, default='PENDING', null=False)
    command_payload = models.JSONField(default=dict, blank=True)
    telemetry = models.JSONField(default=dict, blank=True)
    error_message = models.CharField(max_length=256, null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=False)
    updated_at = models.DateTimeField(auto_now=True, null=False)

    class Meta:
        ordering = ['id']


class CommandOutbox(models.Model):
    id = models.AutoField(primary_key=True, null=False)
    job = models.ForeignKey(
        BatchJob, on_delete=models.CASCADE, null=True, blank=True, related_name='outbox_messages'
    )
    step_execution = models.ForeignKey(
        BatchStepExecution, on_delete=models.CASCADE, null=True, blank=True, related_name='outbox_messages'
    )
    topic = models.CharField(max_length=128, null=False)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=OUTBOX_STATUS_CHOICES, default='QUEUED', null=False)
    sent_at = models.DateTimeField(null=True, blank=True)
    acked_at = models.DateTimeField(null=True, blank=True)
    error_message = models.CharField(max_length=256, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=False)
    updated_at = models.DateTimeField(auto_now=True, null=False)


class TelemetryIngest(models.Model):
    id = models.AutoField(primary_key=True, null=False)
    job = models.ForeignKey(BatchJob, on_delete=models.SET_NULL, null=True, blank=True, related_name='telemetry_records')
    step_execution = models.ForeignKey(
        BatchStepExecution, on_delete=models.SET_NULL, null=True, blank=True, related_name='telemetry_records'
    )
    device_type = models.CharField(max_length=32, null=True, blank=True)
    device_id = models.CharField(max_length=64, null=True, blank=True)
    topic = models.CharField(max_length=128, null=False)
    payload = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(auto_now_add=True, null=False)


class ExperimentDataPoint(models.Model):
    """结构化实验数据点：从原始 TelemetryIngest 中抽取可查询指标。"""
    id = models.AutoField(primary_key=True, null=False)
    job = models.ForeignKey(BatchJob, on_delete=models.SET_NULL, null=True, blank=True, related_name='data_points')
    step_execution = models.ForeignKey(
        BatchStepExecution, on_delete=models.SET_NULL, null=True, blank=True, related_name='data_points'
    )
    telemetry = models.ForeignKey(
        TelemetryIngest, on_delete=models.CASCADE, null=True, blank=True, related_name='data_points'
    )
    device_type = models.CharField(max_length=32, null=True, blank=True)
    device_id = models.CharField(max_length=64, null=True, blank=True)
    metric_name = models.CharField(max_length=64, null=False, db_index=True)
    metric_value = models.FloatField(null=True, blank=True)
    metric_text = models.CharField(max_length=128, null=True, blank=True)
    unit = models.CharField(max_length=32, null=True, blank=True)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=False)

    class Meta:
        ordering = ['timestamp', 'id']
        indexes = [
            models.Index(fields=['job', 'metric_name']),
            models.Index(fields=['step_execution', 'metric_name']),
            models.Index(fields=['device_id', 'metric_name']),
        ]


DEVICE_STATUS_CHOICES = (
    ('idle', 'Idle'),
    ('busy', 'Busy'),
    ('estopped', 'E-Stopped'),
    ('offline', 'Offline'),
    ('error', 'Error'),
    ('completed', 'Completed'),
)


class Device(models.Model):
    """设备注册表：支持多 ESP32-S3 的发现、状态追踪与急停管理。"""
    device_id = models.CharField(max_length=32, unique=True, null=False, help_text='逻辑标识，如 esp32_1')
    client_id = models.CharField(max_length=64, blank=True, help_text='MQTT Client ID，如 ESP32S3_xxx')
    mac_address = models.CharField(max_length=17, blank=True, help_text='硬件 MAC 地址，后续多设备区分用')
    label = models.CharField(max_length=64, blank=True, help_text='用户自定义别名，如 "反应釜 A"')
    is_registered = models.BooleanField(default=True)
    is_online = models.BooleanField(default=False)
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    task_status = models.CharField(max_length=16, choices=DEVICE_STATUS_CHOICES, default='idle')
    # 当前任务快照：{motor, speed, duration_sec, started_at, expected_finished_at}
    current_task = models.JSONField(default=dict, blank=True)
    # 最新遥测快照：{motor_0: {pwm, pcnt}, motor_1: {...}, temperature: null}
    telemetry = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=False)
    updated_at = models.DateTimeField(auto_now=True, null=False)

    class Meta:
        db_table = 'main_page_device'
        ordering = ['device_id']

    def __str__(self):
        return f'{self.label or self.device_id} ({self.device_id})'


class EmergencyStopLog(models.Model):
    """急停操作审计日志。"""
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='estop_logs')
    triggered_at = models.DateTimeField(auto_now_add=True, null=False)
    triggered_by = models.CharField(max_length=64, blank=True)
    scope = models.CharField(max_length=16, blank=True, help_text='single / multi / broadcast')
    reason = models.TextField(blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = 'main_page_emergency_stop_log'
        ordering = ['-triggered_at']
