# Robo Arm Config
# IP_ADDRESS = '192.168.31.197' # original
IP_ADDRESS = '192.168.110.221'
PORT = 5001

# 固定点位注册表
# 说明：
# 1. 当前阶段以采集到的关节角点位为主，便于直接通过 ElephantRobot/RocketAPI 复现。
# 2. 第二阶段接入 MoveIt 时，可将这些点位作为 named targets / seed states 复用。
WAYPOINTS = {
    'home': [0, -90, 0, -90, 0, 0],
    'safe_a': [0.0, -177.667, 85.816, -90.088, -1.406, 0.176],
    'reactor_hover': [-0.0, -177.667, 84.315, 6.416, -92.637, -19.336],
    'powder_station_above': [126.713, -155.759, 116.206, -140.713, 160.488, 74.531],
    'powder_pick': [126.714, -155.759, 116.206, -51.504, 158.818, 74.531],
    'powder_place': [126.714, -155.759, 116.205, -220.342, 158.818, 74.531],
}

CORD_LIST = {
    'zero': WAYPOINTS['home'],
    'route_1': [WAYPOINTS['safe_a'],
                WAYPOINTS['reactor_hover'],
                WAYPOINTS['safe_a'],
                WAYPOINTS['home']],
                
    'route_2': [WAYPOINTS['powder_station_above'],
                WAYPOINTS['powder_pick'],
                WAYPOINTS['powder_place'],
                WAYPOINTS['powder_pick'],
                WAYPOINTS['powder_place'],
                WAYPOINTS['home']]
}
