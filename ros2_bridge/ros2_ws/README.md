# Platform G2 ROS2 Workspace

这是给 Elephant myCobot Pro600 第一阶段接入准备的最小 ROS2 工作空间骨架。

目标：

1. 保留当前 `pymycobot.ElephantRobot(IP, 5001)` 的 socket 控制方式。
2. 在其外层包一层 ROS2 ActionServer，供 Bridge 与 Django 统一调度。
3. 优先打通 `MOVE_ARM -> ExecuteWaypointTrajectory.action` 真机闭环。

## 目录

```text
ros2_ws/
  src/
    platfrom_g2_interfaces/
    arm_socket_driver/
    mycobot_pro600_description/
    mycobot_pro600_gazebo/
```

## 部署建议

推荐将整个仓库同步到树莓派，例如：

```bash
~/Platform_G2/
  peripherals/
  ros2_bridge/
```

这样 `arm_socket_driver_node.py` 可以直接复用仓库中的：

- `peripherals/robo_arm_driver.py`
- `peripherals/robo_arm_config.py`

## 树莓派准备

1. 安装 ROS2 Python 环境。
2. 确保树莓派本机能正常访问 Pro600 控制服务。
3. 先独立验证 socket 基线：

```bash
cd ~/Platform_G2/peripherals
python fixed_waypoint_arm_test.py
```

若这一步不能稳定执行，先不要继续 ROS2 封装调试。

## 构建

```bash
cd ~/Platform_G2/ros2_bridge/ros2_ws
source /opt/ros/$ROS_DISTRO/setup.bash
colcon build
source install/setup.bash
```

## 启动机械臂节点

```bash
cd ~/Platform_G2/ros2_bridge/ros2_ws
source /opt/ros/$ROS_DISTRO/setup.bash
source install/setup.bash
ros2 run arm_socket_driver arm_socket_driver_node
```

成功后应能看到：

- ROS2 节点名：`arm01`
- Action 名：`/arm01/execute_waypoint_trajectory`

## 检查接口

```bash
ros2 node list
ros2 action list
ros2 action info /arm01/execute_waypoint_trajectory
```

## 直接发送测试目标

```bash
ros2 action send_goal /arm01/execute_waypoint_trajectory \
  platfrom_g2_interfaces/action/ExecuteWaypointTrajectory \
  "{trajectory: ['home', 'safe_a', 'reactor_hover', 'home'], speed: 1000, request_id: 'manual-test-001'}"
```

预期结果：

1. 机械臂依次经过这些固定点位。
2. 终端可看到 feedback 百分比和当前 waypoint。
3. 最终返回 `success: true`。

## 与 Bridge 的衔接

当上面的 ROS2 action 能稳定执行后，再在上位机开启：

```bash
cd /Users/zhouyuyan/Documents/Platfrom_G2
export ROS2_BRIDGE_USE_RUNTIME=1
python ros2_bridge/main.py
```

后续只需要把 `ros2_bridge/ros2_runtime.py` 中的 stub 替换成真实 `ActionClient`，就可以打通：

`Django -> Bridge -> /arm01/execute_waypoint_trajectory -> Pro600`

## 当前边界

这套骨架当前只解决：

1. Pro600 机械臂固定点位动作统一接入 ROS2。
2. 为后续 Bridge 和状态机调度提供标准 Action 入口。

还未覆盖：

1. 夹爪独立 ROS2 驱动
2. MoveIt 规划接入
3. 真实 Bridge ActionClient 实现

## Pro600 仿真迁移骨架

当前工作区已经补了两层迁移骨架：

1. `mycobot_pro600_description`
   - 提供 ROS2 可直接启动的 `xacro`
   - 当前是简化几何体版本，便于先打通 `robot_state_publisher / rviz2 / gazebo_ros2_control`
   - 自带 `scripts/import_ros1_assets.py`，用于把官方 `mycobot_ros/noetic/mycobot_pro` 的 `urdf / meshes / scripts` 同步进来做比对

2. `mycobot_pro600_gazebo`
   - 重写了 ROS2 `gazebo.launch.py`
   - 提供 `controllers.yaml`
   - 使用 `joint_state_broadcaster + joint_trajectory_controller`

### 先跑 RViz

```bash
cd ~/Platform_G2/ros2_bridge/ros2_ws
source /opt/ros/$ROS_DISTRO/setup.bash
colcon build
source install/setup.bash
ros2 launch mycobot_pro600_description display.launch.py
```

### 再跑 Gazebo

```bash
cd ~/Platform_G2/ros2_bridge/ros2_ws
source /opt/ros/$ROS_DISTRO/setup.bash
source install/setup.bash
ros2 launch mycobot_pro600_gazebo gazebo.launch.py
```

### 导入官方 ROS1 资产

若你本地已经下载了官方仓库，可执行：

```bash
cd ~/Platform_G2/ros2_bridge/ros2_ws/src/mycobot_pro600_description
python3 scripts/import_ros1_assets.py --ros1-root ~/Downloads/mycobot_ros/mycobot_pro
```

导入后会把官方资产放到：

- `mycobot_pro600_description/vendor_ros1/`
- `mycobot_pro600_gazebo/vendor_ros1/`

如果你使用 sparse-checkout，只拉 `mycobot_600` 和 `mycobot_600_moveit` 还不够。官方 Pro600 的 URDF 会引用：

```text
package://mycobot_description/urdf/mycobot_pro_600/*.dae
```

因此还需要补拉 `mycobot_description`：

```bash
cd ~/Documents/mycobot_ros_noetic
git sparse-checkout set mycobot_pro/mycobot_600 mycobot_pro/mycobot_600_moveit mycobot_description
git pull origin noetic
```

然后重新导入：

```bash
cd ~/Platform_G2/ros2_bridge/ros2_ws/src/mycobot_pro600_description
python3 scripts/import_ros1_assets.py --ros1-root ~/Documents/mycobot_ros_noetic
```

当前策略是：

1. 先让 ROS2 launch / controller / plugin 骨架可维护。
2. ROS2 launch 默认使用 `urdf/pro600_official_assets.urdf.xacro`，它保留官方 Pro600 的 link、joint、collision 和 mesh 引用，并补了 ROS2 control。
3. 不直接把 ROS1 launch 原样搬过来，避免把 ROS1 依赖残留到 ROS2 工作区。
