#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Created: 2016-08-13

@author: pymancer

testing cloud functions
- based on web responses, which should be enough in most cases
- correct email credentials should be used to establish a connection with the cloud
- credentials could be obtained from the config file or shell
- shell credentials will always take precedence over config
- test_add_file and test_create_folder will leave your cloud with empty an empty file
  and folder in the recycle bin, that's why those tests do no run by default even with --web marker


example run from shell:
py.test --email=your_email@mail.ru --password=your_password test_cloud_funcs.py --runweb
to run test_add_file and test_add_file add --rundirty shell parameter
"""
import os
import pytest
import requests
import os.path
from conftest import get_unique_string

pytestmark = pytest.mark.skipif(
    not pytest.config.getoption("--runweb"),
    reason="need --runweb option to run"
)

dirty = pytest.mark.skipif(
    not pytest.config.getoption("--rundirty"),
    reason="need --rundirty option to run"
)

@pytest.fixture(scope='function')
def upload(request, email, password, monkeypatch):
    if email:
        monkeypatch.setattr('upload.LOGIN', email)
    if password:
        monkeypatch.setattr('upload.PASSWORD', password)
    import upload
    return upload


@pytest.fixture(scope='function')
def session(request, upload):
    s = requests.Session()
    upload.cloud_auth(s, login=upload.LOGIN, password=upload.PASSWORD)
    def close_session():
        s.close()
    request.addfinalizer(close_session)
    return s


@pytest.fixture(scope='function')
def token(request, upload, session):
    return upload.get_csrf(session)


@pytest.fixture(scope='function')
def file(request):
    file = os.path.join('.', 'test_file_' + get_unique_string() + '.txt')
    with open(file, mode='w') as f:
        f.write('mail.ru-uploader test file contents')
    def remove_file():
        os.unlink(file)
    request.addfinalizer(remove_file)
    return file


def test_cloud_auth(upload):
    with requests.Session() as s:
        assert upload.cloud_auth(s, login=upload.LOGIN, password=upload.PASSWORD), 'cloud authorization failed'


def test_get_csrf(upload, session):
    assert len(upload.get_csrf(session)) == 32, 'invalid csrf'


def test_get_upload_domain(upload, session, token):
    assert upload.get_upload_domain(session, csrf=token), 'upload domain request failed'


def test_get_cloud_space(upload, session, token):
    assert upload.get_cloud_space(session, csrf=token, login=upload.LOGIN) > 0, 'cloud space fetching failed'


@dirty
def test_create_folder(upload, session, token):
    folder_path = '/' + 'test_folder_' + get_unique_string()
    assert upload.create_folder(session, folder=folder_path, csrf=token), 'folder creation failed'
    assert upload.remove_object(session, obj=folder_path, csrf=token), 'folder removal failed'


@dirty
def test_add_file(upload, session, token, file):
    """ testing with post_file as precondition """
    domain = upload.get_upload_domain(session, csrf=token)
    hash, size = upload.post_file(session, domain=domain, file=file, login=upload.LOGIN)
    assert len(hash) == 40, 'invalid file hash'
    assert size >= 0, 'invalid file size'
    cloud_file = '/' + os.path.basename(file)
    assert upload.add_file(session, file=cloud_file, hash=hash, size=size, csrf=token), 'file addition failed'
    assert upload.remove_object(session, obj=cloud_file, csrf=token), 'file removal failed'
    