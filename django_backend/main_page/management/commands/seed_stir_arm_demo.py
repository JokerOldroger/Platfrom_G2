from django.core.management.base import BaseCommand

from main_page.mqtt import _device_control_topic
from main_page.models import MaterialRecipe, MaterialType, RecipeStep


class Command(BaseCommand):
    help = 'Create or update the minimal stir chamber + Pro600 arm orchestration demo recipe.'

    def add_arguments(self, parser):
        parser.add_argument('--material-name', default='StirArmDemo')
        parser.add_argument('--recipe-version', type=int, default=1)
        parser.add_argument('--esp32-device-id', default='esp32_7cdfa1e6d3cc')
        parser.add_argument('--motor-id', type=int, default=1)
        parser.add_argument('--motor-topic', default=None)
        parser.add_argument('--stirring-speed-rpm', type=int, default=60)
        parser.add_argument('--fixed-rotations', type=float, default=1.0)
        parser.add_argument(
            '--duration-sec',
            '--spinning-time-sec',
            dest='duration_sec',
            type=int,
            default=None,
            help='Explicit motor running time in seconds. If omitted, duration is computed from fixed rotations and rpm.',
        )
        parser.add_argument('--hover-waypoint', default='reactor_hover')
        parser.add_argument('--arm-device-id', default='arm01')

    def handle(self, *args, **options):
        esp32_device_id = options['esp32_device_id']
        motor_topic = options['motor_topic'] or _device_control_topic(esp32_device_id)
        material, _created = MaterialType.objects.update_or_create(
            name=options['material_name'],
            defaults={
                'description': 'Minimal demo recipe for MQTT motor + ROS2 Pro600 arm orchestration.',
                'is_active': True,
            },
        )
        recipe, _created = MaterialRecipe.objects.update_or_create(
            material_type=material,
            version=options['recipe_version'],
            defaults={
                'is_active': True,
                'notes': (
                    'Auto-seeded demo: timed motor run, then arm hover waypoint.'
                    if options['duration_sec'] is not None else
                    'Auto-seeded demo: fixed motor rotations, then arm hover waypoint.'
                ),
                'stirring_speed_rpm': options['stirring_speed_rpm'],
                'stirring_duration_min': None,
            },
        )
        stir_parameters = {
            'topic': motor_topic,
            'device': 'esp32',
            'device_id': esp32_device_id,
            'motor': options['motor_id'],
            'speed_key': 'stirring_speed_rpm',
            'resource_locks': ['stir_chamber:chamber01'],
        }
        if options['duration_sec'] is not None:
            stir_parameters['duration_sec'] = options['duration_sec']
        else:
            stir_parameters['fixed_rotations'] = options['fixed_rotations']

        RecipeStep.objects.update_or_create(
            recipe=recipe,
            step_no=1,
            defaults={
                'step_type': 'STIR',
                'name': 'Run stir chamber timed motor' if options['duration_sec'] is not None else 'Run stir chamber fixed rotations',
                'expected_duration_sec': options['duration_sec'],
                'parameters': stir_parameters,
            },
        )
        RecipeStep.objects.update_or_create(
            recipe=recipe,
            step_no=2,
            defaults={
                'step_type': 'MOVE_ARM',
                'name': 'Move Pro600 to reactor hover',
                'expected_duration_sec': 30,
                'parameters': {
                    'transport': 'ros2',
                    'device': 'roboarm',
                    'device_id': options['arm_device_id'],
                    'action_name': 'arm.execute_trajectory',
                    'goal': {'trajectory': [options['hover_waypoint']]},
                    'depends_on_steps': [1],
                    'resource_locks': [f"roboarm:{options['arm_device_id']}"],
                },
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                'Created/updated demo recipe '
                f'id={recipe.id}, material={material.name}, version={recipe.version}, '
                f'esp32_device_id={esp32_device_id}, motor_topic={motor_topic}, '
                f"duration_sec={options['duration_sec']}, fixed_rotations={options['fixed_rotations']}."
            )
        )
