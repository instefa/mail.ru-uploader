#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Created: 2016-08-12

@author: pymancer

testing main app circle
- no cloud connection required
- pretending cloud related functions are impeccable and config is ok

example run (from shell):
py.test test_main.py
"""
import os
import pytest
import shutil
import os.path
from uuid import uuid1

#import upload
#from upload import main


def get_unique_string():
    return uuid1().urn[9:]


@pytest.fixture(scope='function')
def upload_tearup(request, monkeypatch):
    """ preparing testing environment - pretty obvious, isn't it?
    - creating directory tree with files to upload,
    - setting up config
    - faking cloud functions responses
    - setting up logging
    tree structure:
    ./upload_dir/l0_1.txt
    ./upload_dir/l0_2.txt
    ./upload_dir/level1_1/l1_1_1.txt
    ./upload_dir/level1_1/level2_1/l2_1_1.txt
    ./upload_dir/level1_1/level2_2/level3_1/l3_1_1.txt
    ./upload_dir/level1_2/l1_2_1.txt
    ./upload_dir/level1_2/l1_2_2.txt
    """
    # creating tree
    upload_dir = os.path.join('.', 'test_upload_' + get_unique_string())
    os.makedirs(upload_dir)
    open(os.path.join(upload_dir, 'l0_1.txt'), 'w').close()
    open(os.path.join(upload_dir, 'l0_2.txt'), 'w').close()
    dir = os.path.join(upload_dir, 'level1_1')
    os.makedirs(dir)
    open(os.path.join(dir, 'l1_1_1.txt'), 'w').close()
    dir = os.path.join(dir, 'level2_1')
    os.makedirs(dir)
    open(os.path.join(dir, 'l2_1_1.txt'), 'w').close()
    dir = os.path.join(dir, 'level2_2/level3_1')
    os.makedirs(dir)
    open(os.path.join(dir, 'l3_1_1.txt'), 'w').close()
    dir = os.path.join(upload_dir, 'level1_2')
    os.makedirs(dir)
    open(os.path.join(dir, 'l1_2_1.txt'), 'w').close()
    open(os.path.join(dir, 'l1_2_2.txt'), 'w').close()
    # setting up config (writing file? why? it will not be applied anyway)
    config_file = os.path.join('.', 'test_config_' + get_unique_string())
    uploaded_dir = os.path.join('.', 'test_uploaded_' + get_unique_string())
    with open(config_file, 'w') as f:
        f.write("""[Credentials]
Email : some_email@mail.ru
Password : some_pass

[Locations]
UploadedPath : {}
CloudPath : /backups
UploadPath : {}

[Behaviour]
MoveUploaded : yes
RemoveUploaded : yes
ArchiveFiles : yes
RemoveFolders: yes""".format(uploaded_dir, upload_dir))
    monkeypatch.setattr('upload.IS_CONFIG_PRESENT', True)
    monkeypatch.setattr('upload.CONFIG_FILE', config_file)
    monkeypatch.setattr('upload.UPLOAD_PATH', upload_dir)
    monkeypatch.setattr('upload.UPLOADED_PATH', uploaded_dir)
    monkeypatch.setattr('upload.MOVE_UPLOADED', True)
    # faking cloud functions responses
    def cloud_auth(session, login=None, password=None):
        return True
    monkeypatch.setattr('upload.cloud_auth', cloud_auth)
    def get_csrf(session):
        return 'fake_csrf'
    monkeypatch.setattr('upload.get_csrf', get_csrf)
    def get_upload_domain(session, csrf=''):
        return 'fake_upload_domain'
    monkeypatch.setattr('upload.get_upload_domain', get_upload_domain)
    def get_cloud_space(session, csrf=''):
        return 1*1024*1024*1024
    monkeypatch.setattr('upload.get_cloud_space', get_cloud_space)
    def post_file(session, domain='', file=''):
        return ('1234567890123456789012345678901234567890', 100)
    monkeypatch.setattr('upload.post_file', post_file)
    def add_file(session, file='', hash='', size=0, csrf=''):
        return True
    monkeypatch.setattr('upload.add_file', add_file)
    def create_folder(session, folder='', csrf=''):
        return True
    monkeypatch.setattr('upload.create_folder', create_folder)
    # setting up logging
    log_file = os.path.join('.', 'test_log_' + get_unique_string())
    monkeypatch.setattr('upload.LOG_FILE', log_file)
    def upload_teardown():
        shutil.rmtree(upload_dir)
        os.unlink(config_file)
        shutil.rmtree(uploaded_dir)
        os.unlink(log_file)
    request.addfinalizer(upload_teardown)


def test_main_loop(upload_tearup, capsys):
    import upload
    upload.main()
    out, err = capsys.readouterr()
    assert '7 file(s) uploaded.' in out
