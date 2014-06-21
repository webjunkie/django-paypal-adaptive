#!/usr/bin/env python

from setuptools import setup, find_packages
import paypaladaptive

setup(
    name='django-paypal-adaptive',
    version=".".join(map(str, paypaladaptive.__version__)),
    author='Greg McGuire',
    author_email='greg@buzzcar.com',
    maintainer='Anton Agestam',
    maintainer_email="msn@antonagestam.se",
    url='http://github.com/FundedByMe/django-paypal-adaptive',
    install_requires=[
        'Django>=1.4.3',
        'python-dateutil==2.1',
        'django-money',
    ],
    extras_require={
        'delayed-updates': ['celery>=3.0.12'],
    },
    description='A pluggable Django application for integrating PayPal '
                'Adaptive Payments',
    packages=find_packages(),
    include_package_data=True,
    classifiers=[
        "Framework :: Django",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Operating System :: OS Independent",
        "Topic :: Software Development"
    ],
)
