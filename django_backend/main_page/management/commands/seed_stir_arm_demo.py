from django.core.management.base import BaseCommand

from main_page.recipe_seeds import upsert_stir_arm_demo_recipe


class Command(BaseCommand):
    help = 'Create or update the minimal stir chamber + Pro600 arm orchestration demo recipe.'

    def add_arguments(self, parser):
        parser.add_argument('--material-name', default='StirArmDemo')
        parser.add_argument('--recipe-name', default='Stir Arm Demo')
        parser.add_argument('--recipe-version', type=int, default=1)
        parser.add_argument('--esp32-device-id', default='esp32_7cdfa1e6d3cc')
        parser.add_argument('--motor-id', type=int, default=1)
        parser.add_argument('--motor-topic', default=None)
        parser.add_argument('--stirring-speed-rpm', type=int, default=60)
        parser.add_argument('--reaction-temperature-c', type=float, default=None)
        parser.add_argument('--stirring-duration-min', type=int, default=None)
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
        parser.add_argument(
            '--arm-trajectory',
            nargs='+',
            default=None,
            help='Waypoint trajectory, for example: --arm-trajectory home reactor_hover',
        )
        parser.add_argument('--arm-device-id', default='arm01')

    def handle(self, *args, **options):
        seed = upsert_stir_arm_demo_recipe(
            material_name=options['material_name'],
            recipe_name=options['recipe_name'],
            recipe_version=options['recipe_version'],
            esp32_device_id=options['esp32_device_id'],
            motor_id=options['motor_id'],
            motor_topic=options['motor_topic'],
            stirring_speed_rpm=options['stirring_speed_rpm'],
            duration_sec=options['duration_sec'],
            fixed_rotations=options['fixed_rotations'],
            reaction_temperature_c=options['reaction_temperature_c'],
            stirring_duration_min=options['stirring_duration_min'],
            hover_waypoint=options['hover_waypoint'],
            arm_trajectory=options['arm_trajectory'],
            arm_device_id=options['arm_device_id'],
        )
        recipe = seed['recipe']
        material = seed['material']

        self.stdout.write(
            self.style.SUCCESS(
                'Created/updated demo recipe '
                f'id={recipe.id}, material={material.name}, recipe={recipe.name}, version={recipe.version}, '
                f"esp32_device_id={options['esp32_device_id']}, motor_topic={seed['motor_topic']}, "
                f"duration_sec={options['duration_sec']}, fixed_rotations={options['fixed_rotations']}, "
                f"arm_trajectory={seed['arm_trajectory']}."
            )
        )
