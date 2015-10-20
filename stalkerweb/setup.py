#!/usr/bin/env python
""" setuptools for stalkerweb """

from setuptools import setup, find_packages
from stalkerweb import __version__ as version

setup(
    name='stalkerweb',
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
    install_requires=[
        'stalkerutils==2.0.2',
    ],
    include_package_data=True,
    zip_safe=False,
    scripts=['bin/stalker-web',],
    data_files=[('share/doc/stalkerweb',
                 ['README.md', 'INSTALL',
                  'etc/stalker-web.conf',
                  'etc/init.d/stalker-web',
                 ])]
)
