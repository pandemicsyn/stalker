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
        'eventlet==0.17.4',
        'flask==0.10.1',
        'redis==2.10.3',
        'pymongo==3.0.3',
        'mmh3==2.3.1',
        'flask-rethinkdb==0.2',
        'rethinkdb==2.1.0.post2',
        'flask-bcrypt==0.7.1',
        'flask-wtf==0.12',
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
