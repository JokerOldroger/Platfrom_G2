from decimal import Decimal

from .mqtt import _device_control_topic
from .models import MaterialRecipe, MaterialType, RecipeStep


def _optional_decimal(value):
    if value in (None, ''):
        return None
    return Decimal(str(value))


def _normalise_trajectory(trajectory=None, hover_waypoint=None):
    if trajectory:
        if isinstance(trajectory, str):
            points = [point.strip() for point in trajectory.split(',')]
        else:
            points = [str(point).strip() for point in trajectory]
        points = [point for point in points if point]
        if points:
            return points
    return [hover_waypoint or 'reactor_hover']


def upsert_stir_arm_demo_recipe(
    *,
    material_name='StirArmDemo',
    recipe_name='Stir Arm Demo',
    recipe_version=1,
    esp32_device_id='esp32_7cdfa1e6d3cc',
    motor_id=1,
    motor_topic=None,
    stirring_speed_rpm=60,
    duration_sec=None,
    fixed_rotations=1.0,
    reaction_temperature_c=None,
    stirring_duration_min=None,
    hover_waypoint='reactor_hover',
    arm_trajectory=None,
    arm_device_id='arm01',
):
    motor_topic = motor_topic or _device_control_topic(esp32_device_id)
    trajectory = _normalise_trajectory(arm_trajectory, hover_waypoint)
    duration_sec = int(duration_sec) if duration_sec not in (None, '') else None

    material, _material_created = MaterialType.objects.update_or_create(
        name=material_name,
        defaults={
            'description': 'Configurable demo recipe for MQTT motor + ROS2 Pro600 arm orchestration.',
            'is_active': True,
        },
    )
    recipe, _recipe_created = MaterialRecipe.objects.update_or_create(
        material_type=material,
        version=int(recipe_version),
        defaults={
            'name': recipe_name,
            'is_active': True,
            'notes': (
                'Frontend/CLI configurable demo: timed motor run, then Pro600 waypoint trajectory.'
                if duration_sec is not None else
                'Frontend/CLI configurable demo: fixed motor rotations, then Pro600 waypoint trajectory.'
            ),
            'reaction_temperature_c': _optional_decimal(reaction_temperature_c),
            'stirring_speed_rpm': int(stirring_speed_rpm),
            'stirring_duration_min': (
                int(stirring_duration_min) if stirring_duration_min not in (None, '') else None
            ),
        },
    )

    stir_parameters = {
        'topic': motor_topic,
        'device': 'esp32',
        'device_id': esp32_device_id,
        'motor': int(motor_id),
        'speed_key': 'stirring_speed_rpm',
        'resource_locks': ['stir_chamber:chamber01'],
    }
    if duration_sec is not None:
        stir_parameters['duration_sec'] = duration_sec
    else:
        stir_parameters['fixed_rotations'] = float(fixed_rotations)

    stir_step, _stir_created = RecipeStep.objects.update_or_create(
        recipe=recipe,
        step_no=1,
        defaults={
            'step_type': 'STIR',
            'name': 'Run stir chamber timed motor' if duration_sec is not None else 'Run stir chamber fixed rotations',
            'expected_duration_sec': duration_sec,
            'parameters': stir_parameters,
        },
    )
    arm_step, _arm_created = RecipeStep.objects.update_or_create(
        recipe=recipe,
        step_no=2,
        defaults={
            'step_type': 'MOVE_ARM',
            'name': 'Move Pro600 waypoint trajectory',
            'expected_duration_sec': 30,
            'parameters': {
                'transport': 'ros2',
                'device': 'roboarm',
                'device_id': arm_device_id,
                'action_name': 'arm.execute_trajectory',
                'goal': {'trajectory': trajectory},
                'depends_on_steps': [1],
                'resource_locks': [f'roboarm:{arm_device_id}'],
            },
        },
    )

    return {
        'material': material,
        'recipe': recipe,
        'steps': [stir_step, arm_step],
        'motor_topic': motor_topic,
        'arm_trajectory': trajectory,
    }
