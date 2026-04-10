#!/usr/bin/env bash
set -e

cd ~/rav/robotics_ws

export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 launch rav_nav2 rav_nav.launch.py