from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

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
    avaliable = models.BooleanField(default=True)
    description = models.CharField(max_length=256)

DEVICE_CHOICES = (
    (1, 'ESP32S3_1'),
    (2, 'ESP32S3_2'),
    (3, 'ESP32S3_3'),
    (4, 'ESP32S3_4')
)
DEFAULT_DEVICE = 1

EVENT_STATUS = (
    (1, 'Active'),
    (2, 'Done')
)
DEFAULT_EVENT_STATUS = 1

class MotorEvent(models.Model):
    id = models.AutoField(primary_key=True, null=False)
    timestamp = models.DateTimeField(auto_now_add=True, null=False)
    device_id = models.IntegerField(choices=DEVICE_CHOICES, default=DEFAULT_DEVICE)
    motor = models.IntegerField(null=False)
    speed = models.IntegerField(null=False)
    time  = models.IntegerField(null=False)
    statue = models.IntegerField(choices=EVENT_STATUS, default=DEFAULT_EVENT_STATUS)


MOTOR_CHOICES = (
    (1, 'Motor_0'),
    (2, 'Motor_1'),
    (3, 'Motor_2'),
    (4, 'Motor_3'),
)
DEFAULT_MOTOR = 1
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


class Spinning(models.Model):
    id = models.AutoField(primary_key=True, null=False)
    motor_name = models.CharField(max_length=128, null=False)
    scheduled_time = models.DateTimeField(null=False)
    motor_speed = models.IntegerField(null=False)
    duration_sec = models.IntegerField(null=False)

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
