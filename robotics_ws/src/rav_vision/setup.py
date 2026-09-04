from glob import glob
from setuptools import find_packages, setup

package_name = 'rav_vision'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md', 'requirements.txt']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
        ('share/' + package_name + '/scripts', glob('scripts/*.sh')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    description='Treinamento e validacao de datasets com YOLO26 no ROS 2 Humble.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'realtime_inference = rav_vision.realtime_inference:main',
            'realtime_3d_inference = rav_vision.realtime_3d_inference:main',
            'vision_pick_bridge = rav_vision.vision_pick_bridge:main',
            'yolo26_train = rav_vision.train_yolo26:main',
            'yolo26_val = rav_vision.val_yolo26:main',
            'rav_dataset_check = rav_vision.dataset_check:main',
	    'rav_vision_realtime = rav_vision.realtime_inference:main',
        ],
    },
)
