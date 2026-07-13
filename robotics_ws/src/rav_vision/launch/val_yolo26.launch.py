from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    data = LaunchConfiguration('data')
    model = LaunchConfiguration('model')
    imgsz = LaunchConfiguration('imgsz')
    batch = LaunchConfiguration('batch')
    device = LaunchConfiguration('device')
    split = LaunchConfiguration('split')
    project = LaunchConfiguration('project')
    name = LaunchConfiguration('name')

    return LaunchDescription([
        DeclareLaunchArgument('data', default_value='src/rav_vision/config/rav_dataset.yaml'),
        DeclareLaunchArgument('model', default_value='runs/rav_vision/train/yolo26_rav/weights/best.pt'),
        DeclareLaunchArgument('imgsz', default_value='640'),
        DeclareLaunchArgument('batch', default_value='8'),
        DeclareLaunchArgument('device', default_value='0'),
        DeclareLaunchArgument('split', default_value='val'),
        DeclareLaunchArgument('project', default_value='runs/rav_vision/val'),
        DeclareLaunchArgument('name', default_value='yolo26_rav_val'),
        ExecuteProcess(
            cmd=[
                'ros2', 'run', 'rav_vision', 'yolo26_val',
                '--data', data,
                '--model', model,
                '--imgsz', imgsz,
                '--batch', batch,
                '--device', device,
                '--split', split,
                '--project', project,
                '--name', name,
            ],
            output='screen',
        ),
    ])
