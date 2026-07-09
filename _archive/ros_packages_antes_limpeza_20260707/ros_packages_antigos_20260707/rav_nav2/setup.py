from setuptools import setup
from glob import glob
import os

package_name = 'rav_nav2'

setup(
    name=package_name,
    version='0.0.0',
    packages=[package_name],
    data_files=[
        # Registra o pacote no índice do ROS2
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        
        # Instala o package.xml
        (os.path.join('share', package_name), ['package.xml']),
        
        # Instala arquivos de Launch
        (os.path.join('share', package_name, 'launch'), 
            glob(os.path.join('launch', '*.launch.py'))),
        
        # Instala arquivos de Configuração e Parâmetros (.yaml, .lua, etc)
        (os.path.join('share', package_name, 'config'), 
            glob(os.path.join('config', '*'))),
        
        # Instala Mapas (.yaml e .pgm)
        (os.path.join('share', package_name, 'maps'), 
            glob(os.path.join('maps', '*'))),
            
        # Instala arquivos de visualização do RViz (.rviz)
        (os.path.join('share', package_name, 'rviz'), 
            glob(os.path.join('rviz', '*'))),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='nathan',
    maintainer_email='nathan@email.com',
    description='RAV navigation package using Nav2',
    license='TODO',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            # Espaço reservado para scripts python executáveis, se necessário
        ],
    },
)