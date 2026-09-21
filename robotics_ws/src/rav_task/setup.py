from glob import glob
from setuptools import find_packages, setup

package_name = 'rav_task'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'requirements.txt']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    description='Orquestra pick-and-place do RAF: ponte WebSocket com o RavPlatform.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'start_task = rav_task.start_task:main',
        ],
    },
)
