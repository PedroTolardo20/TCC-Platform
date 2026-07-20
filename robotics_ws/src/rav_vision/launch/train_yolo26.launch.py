from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    data = LaunchConfiguration('data')
    model = LaunchConfiguration('model')
    epochs = LaunchConfiguration('epochs')
    imgsz = LaunchConfiguration('imgsz')
    batch = LaunchConfiguration('batch')
    device = LaunchConfiguration('device')
    project = LaunchConfiguration('project')
    name = LaunchConfiguration('name')

    return LaunchDescription([
        DeclareLaunchArgument('data', default_value='src/rav_vision/config/rav_dataset.yaml'),
        DeclareLaunchArgument('model', default_value='yolo26n.pt'),
        DeclareLaunchArgument('epochs', default_value='100'),
        DeclareLaunchArgument('imgsz', default_value='640'),
        DeclareLaunchArgument('batch', default_value='8'),
        DeclareLaunchArgument('device', default_value='0'),
        DeclareLaunchArgument('project', default_value='runs/rav_vision/train'),
        DeclareLaunchArgument('name', default_value='yolo26_rav'),
        ExecuteProcess(
            cmd=[
                'ros2', 'run', 'rav_vision', 'yolo26_train',
                '--data', data,
                '--model', model,
                '--epochs', epochs,
                '--imgsz', imgsz,
                '--batch', batch,
                '--device', device,
                '--project', project,
                '--name', name,
            ],
            output='screen',
        ),
    ])
