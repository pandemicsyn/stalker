#!/usr/bin/env python

import os
from sys import argv
from setuptools import setup, find_packages
from stalker import __version__ as version

install_requires = []

name = "stalker-agent"

data_files = [('share/doc/stalker',
               ['README.md', 'INSTALL',
                'etc/stalker-agent.conf',
                'etc/init.d/stalker-agent',
                'etc/stalkerweb.cfg',
                'etc/init.d/stalker-web',
                ])]

if not os.getenv('VIRTUAL_ENV', False) and argv[1] == 'install':
    data_files.append(('/etc/init.d', ['etc/init.d/stalker-agent']))
    data_files.append(('/etc/init.d', ['etc/init.d/stalker-web']))
else:
    data_files.append(('share/doc',
                       ['etc/init.d/stalker-agent']))
    data_files.append(('share/doc',
                       ['etc/init.d/stalker-web']))

setup(
    name=name,
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
    install_requires=install_requires,
    include_package_data=True,
    zip_safe=False,
    scripts=['bin/stalker-agent', 'bin/stalker-web', 'bin/stalker-client', 'bin/stalkly',],
    data_files=data_files)
