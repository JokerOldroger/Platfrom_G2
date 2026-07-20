from setuptools import setup

package_name = 'arm_socket_driver'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Platform G2',
    maintainer_email='devnull@example.com',
    description='ROS2 action server wrapper for Elephant myCobot Pro600 socket API.',
    license='Proprietary',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'arm_socket_driver_node = arm_socket_driver.arm_socket_driver_node:main',
        ],
    },
)
