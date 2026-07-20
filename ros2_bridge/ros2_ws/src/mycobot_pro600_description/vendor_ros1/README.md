这里用于暂存从官方 `mycobot_ros/noetic/mycobot_pro` 导入的参考资产。

建议使用：

```bash
cd ~/Platform_G2/ros2_bridge/ros2_ws/src/mycobot_pro600_description
python3 scripts/import_ros1_assets.py --ros1-root ~/Downloads/mycobot_ros/mycobot_pro
```

导入内容默认不纳入 Git，避免把第三方大文件和未审查资产直接提交进主仓库。
