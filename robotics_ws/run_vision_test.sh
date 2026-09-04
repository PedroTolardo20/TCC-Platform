#!/bin/bash
source /home/nathan/rav/robotics_ws/install/setup.bash
ros2 run rav_vision realtime_3d_inference --ros-args -p model_path:=/home/nathan/rav/robotics_ws/src/rav_vision/models/best_50epochs.pt -p target_frame:=manipulator_world -p device:=cpu
