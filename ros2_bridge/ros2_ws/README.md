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
   - Gazebo 默认使用简化几何体模型，保证渲染和关节控制验证不依赖官方 DAE
   - 官方 Pro600 资产模型继续用于 RViz 展示和后续 mesh 转换
   - 自带 `scripts/import_ros1_assets.py`，用于把官方 `mycobot_ros/noetic/mycobot_pro` 的 `urdf / meshes / scripts` 同步进来做比对

2. `mycobot_pro600_gazebo`
   - 重写了 ROS2 `gazebo.launch.py`
   - 提供 `controllers.yaml`
   - 使用 Jazzy 的 `gz_ros2_control + joint_state_broadcaster + joint_trajectory_controller`

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
sudo apt install ros-$ROS_DISTRO-gz-ros2-control
rm -rf build install log
colcon build --symlink-install
source install/setup.bash
ros2 launch mycobot_pro600_gazebo gazebo.launch.py use_rviz:=false
```

启动成功后，在第二个终端确认控制器和 Action：

```bash
cd ~/Platform_G2/ros2_bridge/ros2_ws
source /opt/ros/$ROS_DISTRO/setup.bash
source install/setup.bash

ros2 control list_controllers
ros2 action info /arm_controller/follow_joint_trajectory
```

预期两个控制器均为 `active`。然后发送一组幅度较小、持续 5 秒的六关节轨迹：

```bash
ros2 action send_goal /arm_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory \
  "{trajectory: {joint_names: [joint1, joint2, joint3, joint4, joint5, joint6], points: [{positions: [0.20, -0.30, 0.25, 0.15, -0.15, 0.20], time_from_start: {sec: 5, nanosec: 0}}]}}" \
  --feedback
```

测试后回到零位：

```bash
ros2 action send_goal /arm_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory \
  "{trajectory: {joint_names: [joint1, joint2, joint3, joint4, joint5, joint6], points: [{positions: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], time_from_start: {sec: 5, nanosec: 0}}]}}" \
  --feedback
```

如需切回官方关节链，可同时指定官方模型和对应控制器文件；当前官方 DAE 在 Gazebo
Ogre2 中仍可能出现 `zero sub-meshes`，因此不作为默认运动验证路径：

```bash
ros2 launch mycobot_pro600_gazebo gazebo.launch.py \
  model:=$PWD/install/mycobot_pro600_description/share/mycobot_pro600_description/urdf/pro600_official_assets.urdf.xacro \
  controllers_file:=$PWD/install/mycobot_pro600_gazebo/share/mycobot_pro600_gazebo/config/controllers_official.yaml
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
