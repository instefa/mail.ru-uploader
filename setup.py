#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
Created: 2016-08-10

@author: pymancer

windows executable cx_Freeze builder config

usage:
python setup.py build
"""

import sys
import requests
from cx_Freeze import setup, Executable


options = {
    'build_exe': {
        'packages': ['requests', 'requests_toolbelt'],
        'include_files' : [(requests.certs.where(), 'cacert.pem')]
    }
}

executables = [
    Executable('upload.py', base='Console')
]

setup(name = "mail.ru-uploader" ,
      version = "0.0.1" ,
      description = "" ,
      options=options,
      executables=executables
      )