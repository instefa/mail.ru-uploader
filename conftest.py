#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Created: 2016-08-13

@author: pymancer

changing testing behaviour
- allowing tests to use shell parameters
"""
import pytest
from uuid import uuid1


def pytest_addoption(parser):
    parser.addoption("--email", action="store", default="", help="full cloud email address")
    parser.addoption("--password", action="store", default="", help="cloud password")
    parser.addoption("--runweb", action="store_true", help="run web tests")
    parser.addoption("--rundirty", action="store_true", help="run web tests with bad cleanup")

@pytest.fixture
def email(request):
    return request.config.option.email

@pytest.fixture
def password(request):
    return request.config.option.password

@pytest.fixture
def runweb(request):
    return request.config.option.runweb

@pytest.fixture
def rundirty(request):
    return request.config.option.rundirty


def get_unique_string():
    return uuid1().urn[9:]