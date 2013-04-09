#!/usr/bin/env python

from setuptools import setup, find_packages

install_requires = []

name = "stalker"

data_files = [('share/doc/stalker',
               ['README.md',
                'etc/stalker-agent.conf',
                'etc/stalker-agent.init',
                'etc/stalker-manager.conf',
                'etc/stalker-manager.init',
                'etc/stalker-runner.conf',
                'etc/stalker-runner.init',
               ])]

setup(
    name = name,
    version = "0.0.5",
    author = "Florian Hines",
    author_email = "syn@ronin.io",
    description = "Simple Monitoring System",
    url = "http://github.com/pandemicsyn/stalker",
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
    scripts=['bin/stalker-agent', 'bin/stalker-manager', 'bin/stalker-runner',
             'bin/stalker-web', 'bin/stalker-client',],
    data_files = data_files)
