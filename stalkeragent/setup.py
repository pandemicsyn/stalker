#!/usr/bin/env python
""" setuptools for stalkeragent """

from setuptools import setup, find_packages
from stalkeragent import __version__ as version

with open('requirements.txt') as f:
    REQUIRED = f.read().splitlines()

setup(
    name='stalkeragent',
    version=version,
    author="Florian Hines",
    author_email="syn@ronin.io",
    description="Simple Monitoring System",
    url="http://github.com/pandemicsyn/stalker",
    packages=find_packages(),
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 2.6',
        'Environment :: No Input/Output (Daemon)',
    ],
    install_requires=[REQUIRED,
                     ],
    include_package_data=True,
    zip_safe=False,
    scripts=['bin/stalker-agent',],
    data_files=[('share/doc/stalkeragent',
                 ['README.md', 'INSTALL',
                  'etc/stalker-agent.conf',
                  'etc/init.d/stalker-agent',
                 ])]
)
