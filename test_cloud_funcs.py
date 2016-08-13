#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Created: 2016-08-13

@author: pymancer

testing cloud functions
- correct email credentials should be used to establish a connection with the cloud
- credentials could be obtained from the config file or shell
- shell credentials will always take precedence over config

example run (from shell):
py.test --email=your_email@mail.ru --password=your_password test_cloud_funcs.py
"""
import pytest
import requests

@pytest.fixture(scope='function')
def upload(request, email, password, monkeypatch):
    if email:
        monkeypatch.setattr('upload.LOGIN', email)
    if password:
        monkeypatch.setattr('upload.PASSWORD', password)
    import upload
    return upload

def test_cloud_auth(upload):
    with requests.Session() as session:
        assert upload.cloud_auth(session, login=upload.LOGIN, password=upload.PASSWORD)
