#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Created: 2016-08-13

@author: pymancer

changing testing behaviour
- allowing tests to use shell parameters
"""
import pytest


def pytest_addoption(parser):
    parser.addoption("--email", action="store", default="", help="full cloud email address")
    parser.addoption("--password", action="store", default="", help="cloud password")

@pytest.fixture
def email(request):
    return request.config.option.email

@pytest.fixture
def password(request):
    return request.config.option.password
