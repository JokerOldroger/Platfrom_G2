# ROS2 Bridge

最小桥接骨架，用于将 Django 的 `transport=ros2` 指令转换为 ROS2
`topic / service / action` 调用。

当前阶段目标：

1. 支持 `MOVE_ARM -> action` 的最小闭环。
2. 提供 `/dispatch/action` 与 `/healthz` HTTP 接口。
3. 生成与 Django `process_device_reply_envelope()` 兼容的 reply envelope。

建议演进路线：

1. 第一阶段：运行 mock bridge，验证 Django -> Bridge -> Django reply 闭环。
2. 第二阶段：在 `ros2_bridge/ros2_runtime.py` 中接入真实 `rclpy` action client。
3. 第三阶段：扩展到 gripper / service / topic。

新增骨架文件：

1. `ros2_runtime.py`
   - Bridge 的 ROS2 runtime 入口。
   - 默认只提供最小 action dispatch 骨架。
   - 通过环境变量 `ROS2_BRIDGE_USE_RUNTIME=1` 启用。
2. `arm01_action_server_demo.py`
   - `arm01` 示例 action server。
   - 内部直接复用 `peripherals/robo_arm_driver.py` 的固定点位控制能力。
   - 用于第一阶段验证 `Bridge -> arm01` 真机执行闭环。

推荐联调顺序：

1. 默认 mock 模式启动 `python ros2_bridge/main.py`
2. 确认 Django `transport=ros2` 请求能命中 `/dispatch/action`
3. 在已 source ROS2 环境中运行 `arm01_action_server_demo.py`
4. 设置 `ROS2_BRIDGE_USE_RUNTIME=1` 后再逐步把 `ros2_runtime.py` 中的 stub 替换成真实 `ActionClient`
