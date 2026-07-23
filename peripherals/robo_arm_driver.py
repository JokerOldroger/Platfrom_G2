from pymycobot import ElephantRobot

try:
    from .robo_arm_config import IP_ADDRESS, PORT, CORD_LIST, WAYPOINTS
except ImportError:
    # 兼容直接在 peripherals 目录下执行脚本的旧用法。
    from robo_arm_config import IP_ADDRESS, PORT, CORD_LIST, WAYPOINTS


class RoboArmControl:
    def __init__(self):
        self.client = ElephantRobot(IP_ADDRESS, PORT)
        self.client.start_client()
        self.running = True

    def end(self):
        self.client.stop_client()
    def to_position(self, angle_list, speed):
        try:
            print(f'[RoboArm] write_angles angle_list={angle_list}, speed={speed}')
            write_ret = self.client.write_angles(angle_list, speed)
            print(f'[RoboArm] write_angles ret={write_ret!r}')

            wait_ret = self.client.command_wait_done()
            print(f'[RoboArm] command_wait_done ret={wait_ret!r}')

            coords = self.client.get_coords()
            print(f'[RoboArm] coords={coords}')

            angles = self.client.get_angles()
            print(f'[RoboArm] angles={angles}')

            return 'Success'
        except Exception as exc:
            import traceback
            print(f'[RoboArm] to_position failed: {exc!r}')
            traceback.print_exc()
            return 'Fail'

    def to_waypoint(self, waypoint_name, speed=1000):
        angle_list = WAYPOINTS.get(waypoint_name)
        if angle_list is None:
            raise ValueError(f'Unknown waypoint: {waypoint_name}')
        print(f'[RoboArm] Moving to waypoint: {waypoint_name} -> {angle_list}')
        return self.to_position(angle_list, speed)

    def to_zero(self):
        # print(CORD_LIST['zero'])
        self.to_position(CORD_LIST['zero'], 1000)
        self.print_position()

    def print_position(self):
        try:
            print(self.client.get_coords())
            print(self.client.get_angles())
            print(self.client.get_speed())
            return 'Success'
        except:
            return 'Fail'

    def route(self, route, speed):
        for point in route:
            self.to_position(point, speed)

    def run_waypoint_sequence(self, waypoint_names, speed=1000):
        for waypoint_name in waypoint_names:
            result = self.to_waypoint(waypoint_name, speed)
            if result != 'Success':
                return result
        return 'Success'

    def main_loop(self):
        while self.running:
            cmd = input('>>>')
            if cmd == 'quit':
                self.end()
                self.running = False
            elif cmd == 'get_pos':
                self.print_position()
            elif cmd == 'to_zero':
                self.to_zero()
            elif cmd == 'r_1':
                self.route(CORD_LIST['route_1'], 1000)
            elif cmd == 'r_2':
                self.route(CORD_LIST['route_2'], 1500)
            elif cmd.startswith('goto '):
                _, waypoint_name = cmd.split(' ', 1)
                self.to_waypoint(waypoint_name.strip(), 1000)


if __name__ == '__main__':
    control = RoboArmControl()
    control.main_loop()
