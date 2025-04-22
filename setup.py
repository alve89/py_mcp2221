# setup.py
# Version: 1.0.2

import os
from setuptools import setup, find_packages

setup(
    name="mcp2221_io",
    version="1.6.3",
    packages=find_packages(),
    install_requires=[
        'paho-mqtt',
        'PyYAML',
        'hidapi',
        'adafruit-blinka',
        'adafruit-circuitpython-busdevice',
        'termcolor'
    ],
    entry_points={
        'console_scripts': [
            'mcp2221-controller=mcp2221_io.main:main',
        ],
    },
    author="Stefan Herzog",
    author_email="your.email@example.com",
    description="MCP2221 IO Controller with MQTT Support",
    long_description=open('README.md').read() if os.path.exists('README.md') else '',
    long_description_content_type="text/markdown",
    keywords="mcp2221, gpio, mqtt, home-assistant",
    url="https://github.com/yourusername/mcp2221_io",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    python_requires=">=3.7",
)