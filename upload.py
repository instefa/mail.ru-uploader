#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Created: 2016-08-09

@author: pymancer

uploads specified directory contents to mail.ru cloud
- same name files in the cloud will NOT be replaced (still zipped and posted though)
- preserves upload directory structure
- only relative paths were tested at this moment
- functions are not designed for import, module needs refactoring to class

requirements (Python 3.5):
pip install requests requests-toolbelt

example run from venv:
python -m upload
"""
import os

import sys
import json
import time
import zlib
import logging
import os.path
import zipfile
import requests
import datetime
import configparser
from shutil import move
from mimetypes import guess_type
from requests_toolbelt import MultipartEncoder
from requests.compat import urljoin, quote_plus
from logging.handlers import RotatingFileHandler

__version__ = '0.0.3'

IS_CONFIG_PRESENT = False # local configuration file presence indicator
CONFIG_FILE = './.config' # configuration file, will be created on the very first use
# trying to load local configuration file
config = configparser.ConfigParser(delimiters=(':'))
config.optionxform=str
if config.read(CONFIG_FILE):
    IS_CONFIG_PRESENT = True

# frozen executable check
IS_FROZEN = getattr(sys, 'frozen', False)

###----- GENERAL CONFIGURATION PARAMETERS-------###
# do not forget to accept https://cloud.mail.ru/LA/ before first use by entering the cloud with browser)
# please, use only forward slashes in path variables
# please, note, that the last three variables in this block are generally are OK without any changes
# full mail.ru email address
LOGIN = config.get('Credentials', 'Email', fallback='your_email@mail.ru')
# email password
PASSWORD = config.get('Credentials', 'Password', fallback='your_email_password')
# absolute cloud path (without 'home')
CLOUD_PATH = config.get('Locations', 'CloudPath', fallback='/backups')
# local folder path with files to upload, use '.' to set path relative to the module location
UPLOAD_PATH = config.get('Locations', 'UploadPath', fallback='./upload')
# local folder to move uploaded files, will be created if not exists
UPLOADED_PATH = config.get('Locations', 'UploadedPath', fallback='./uploaded')
# True, if False - no uploaded files zipping
ARCHIVE_FILES = config.getboolean('Behaviour', 'ArchiveFiles', fallback=True)
# True, if False - old files should be deleted manually before next session
REMOVE_UPLOADED = config.getboolean('Behaviour', 'RemoveUploaded', fallback=True)
# False, if True uploaded files will be moved to UPLOADED_PATH directory, REMOVE_UPLOADED setting will be ignored
MOVE_UPLOADED = config.getboolean('Behaviour', 'MoveUploaded', fallback=False)
# True, will delete empty upload folders, will leave root folder, if False only files will be removed or moved if set
REMOVE_FOLDERS = config.getboolean('Behaviour', 'RemoveFolders', fallback=True)
###--------------------------------------###

LOG_FILE  = './upload.log' # log file path relative to the module location
CLOUD_URL = 'https://cloud.mail.ru/api/v2/'
VERIFY_SSL = True # True, use False only for debug and if you know what you're doing
CLOUD_DOMAIN_ORD = 2 # 2 - practice, 1 - theory
API_VER = 2 # 2 - constant so far
TIME_AMEND = '0246' # '0246', exact meaning has not been quite sorted out yet
CLOUD_CONFLICT = 'strict' # 'strict' - should remain constant at least until 'rename' implementation
MAX_FILE_SIZE = 2*1024*1024*1024 # 2*1024*1024*1024 (bytes ~ 2 GB), API constraint
FILES_TO_PRESERVE = ('application/zip', ) # do not archive already zipped files
QUOTED_LOGIN = quote_plus(LOGIN) # just for convenience
DEFAULT_FILETYPE = 'text/plain' # 'text/plain' is good option
# do not upload this files (only for module's directory)
FILES_TO_SKIP = set((os.path.basename(CONFIG_FILE), os.path.basename(LOG_FILE)))
CACERT_FILE = 'cacert.pem'
LOGGER = None


def get_logger(name, log_file=LOG_FILE):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    # create a file handler
    handler = RotatingFileHandler(LOG_FILE, mode='a', maxBytes=5*1024*1024, backupCount=2, encoding=None, delay=0)
    handler.setLevel(logging.INFO)
    # create a logging format
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    # add the handlers to the logger
    logger.addHandler(handler)
    return logger


def cloud_auth(session, login=LOGIN, password=PASSWORD):
    r = session.post('https://auth.mail.ru/cgi-bin/auth?lang=ru_RU&from=authpopup',
                     data = {'Login': LOGIN, 'Password': PASSWORD, 'page': urljoin(CLOUD_URL, '?from=promo'),
                             'new_auth_form': 1, 'Domain': LOGIN.split('@')[1]}, verify = VERIFY_SSL)
    if r.status_code == requests.codes.ok:
        return True
    elif LOGGER:
        LOGGER.error('Mail authorization request unsuccessful, http code: {}, msg: {}'.format(r.status_code, r.text))
    return None


def get_csrf(session):
    r = session.get(urljoin(CLOUD_URL, 'tokens/csrf'), verify = VERIFY_SSL)
    if r.status_code == requests.codes.ok:
        r_json = r.json()
        return r_json['body']['token']
    elif LOGGER:
        LOGGER.error('CSRF token request unsuccessful, http code: {}, msg: {}'.format(r.status_code, r.text))
    return None


def get_upload_domain(session, csrf=''):
    """ return current cloud's upload domain url """
    url = urljoin(CLOUD_URL, 'dispatcher?token=' + csrf)
    r = session.get(url, verify = VERIFY_SSL)
    if r.status_code == requests.codes.ok:
        r_json = r.json()
        return r_json['body']['upload'][0]['url']
    elif LOGGER:
        LOGGER.error('Upload domain request unsuccessful, http code: {}, msg: {}'.format(r.status_code, r.text))
    return None


def get_cloud_csrf(session):
    if cloud_auth(session):
        return get_csrf(session)
    return None


def get_cloud_space(session, csrf=''):
    """ returns available free space in bytes """
    assert csrf is not None, 'No CSRF token'

    timestamp = str(int(time.mktime(datetime.datetime.now().timetuple())* 1000))
    url = urljoin(CLOUD_URL, 'user/space?api=' + str(API_VER) + '&email=' + QUOTED_LOGIN + '&x-email=' + QUOTED_LOGIN + '&token=' + csrf + '&_=' + timestamp)

    r = session.get(url, verify = VERIFY_SSL)
    if r.status_code == requests.codes.ok:
        r_json = r.json()
        total_bytes = r_json['body']['total'] * 1024 * 1024
        used_bytes = r_json['body']['used'] * 1024 * 1024
        return total_bytes - used_bytes
    return 0

def post_file(session, domain='', file=''):
    """ posts file to the cloud's upload server
    param: file - string filename with path
    """
    assert domain is not None, 'No domain to upload provided'
    assert file is not None, 'No file to upload provided'

    filetype = guess_type(file)[0]
    if not filetype:
        filetype = DEFAULT_FILETYPE
        if LOGGER:
            LOGGER.warning('File {} type unknown, using default: {}'.format(file, DEFAULT_FILETYPE))

    filename = os.path.basename(file)
    timestamp = str(int(time.mktime(datetime.datetime.now().timetuple()))) + TIME_AMEND
    url = urljoin(domain, '?cloud_domain=' + str(CLOUD_DOMAIN_ORD) + '&x-email=' + QUOTED_LOGIN + '&fileapi' + timestamp)
    m = MultipartEncoder(fields={'file': (quote_plus(filename), open(file, 'rb'), filetype)})

    r = session.post(url, data=m, headers={'Content-Type': m.content_type}, verify = VERIFY_SSL)
    if r.status_code == requests.codes.ok:
        if len(r.content):
            hash = r.content[:40].decode()
            size = int(r.content[41:-2])
            return (hash, size)
        elif LOGGER:
            LOGGER.error('File {} post error, no hash and size obtained'.format(file))
    elif LOGGER:
        LOGGER.error('File {} post error, http code: {}, msg: {}'.format(file, r.status_code, r.text))
    return (None, None)


def add_file(session, file='', hash='', size=0, csrf=''):
    """ 'file' should be filename with absolute cloud path """
    assert file is not None, 'No file to upload passed'
    assert len(hash) == 40, 'No hash passed'
    assert size > 0, 'No size passed'
    assert csrf is not None, 'No CSRF token passed'

    url = urljoin(CLOUD_URL, 'file/add')
    # api, email, x-email, x-page-id (not implemented), build (not implemented) - optional parameters
    postdata = {'home': file, 'hash': hash, 'size': size, 'conflict': CLOUD_CONFLICT, 'token': csrf,
                'api': API_VER, 'email':LOGIN, 'x-email': LOGIN}

    r = session.post(url, data=postdata, headers={'Content-Type': 'application/x-www-form-urlencoded'}, verify=VERIFY_SSL)
    if r.status_code == requests.codes.ok:
        return True
    elif LOGGER:
        LOGGER.error('File {} addition error, http code: {}, msg: {}'.format(file, r.status_code, r.text))
    return None


def create_folder(session, folder='', csrf=''):
    """ Takes 'folder' as new folder name with full cloud path (without 'home'),
    returns True even if target folder already existed
    Path should start with forward slash,
    no final slash should be present after the target folder name
    """
    assert folder is not None, 'No folder path provided'
    assert csrf is not None, 'No CSRF provided'
    url = urljoin(CLOUD_URL, 'folder/add')
    # api, email, x-email, x-page-id (not implemented), build (not implemented) - optional parameters
    postdata = {'home': folder, 'conflict': CLOUD_CONFLICT, 'token': csrf,
                'api': API_VER, 'email':LOGIN, 'x-email': LOGIN}
    r = session.post(url, data=postdata, headers={'Content-Type': 'application/x-www-form-urlencoded'}, verify=VERIFY_SSL)
    if r.status_code == requests.codes.ok:
        return True
    elif r.status_code == requests.codes.bad:
        try:
            r_error = r.json()['body']['home']['error']
        except KeyError:
            r_error = None
        if r_error == 'exists':
            if LOGGER:
                LOGGER.warning('Folder {} already exists'.format(folder))
            return True
        elif LOGGER:
            LOGGER.error('Folder {} creating failed, http code 400. Error: {}'.format(r_error))
    elif LOGGER:
        LOGGER.error('Folder {} creating error, http code: {}, msg: {}'.format(folder, r.status_code, r.text))
    return None


def zip_file(file):
    """ creates compressed zip files with same name and 'zip' extension
    on success deletes original file
    on failure returns original file
    replaces existing archives
    param: file - filename with path (string)
    """
    file_path, file_name = os.path.split(file)
    file_root, file_ext = os.path.splitext(file_name)
    zip_name = file_root + '.zip'
    compression = zipfile.ZIP_DEFLATED
    try:
        zf = zipfile.ZipFile(os.path.join(file_path, zip_name), mode='w')
        zf.debug = 0
        # convert unicode file names to byte strings if any
        zf.write(file, arcname=file_name, compress_type=compression)
    except Exception as e:
        zip_name = file_name
        if LOGGER:
            LOGGER.error('Failed to archive {}, error:'.format(file, e))
    else:
        os.unlink(file)
        if LOGGER:
            LOGGER.info('{} archived as {}'.format(file, os.path.join(file_path, zip_name)))
            LOGGER.info('file {} deleted after archiving'.format(file))
    finally:
        zf.close()
    return os.path.join(file_path, zip_name)


def get_dir_files(path=UPLOAD_PATH, space=0):
    """ returns list of the cwd files, follows cloud restrictions """
    assert space is not None, 'No cloud space left or space fetching error'

    for filename in next(os.walk(path))[2]:
        file = os.path.join(path, filename)
        # in case we uploading current directory
        if filename in FILES_TO_SKIP and path == '.':
            continue
        # in case some files are already zipped
        if ARCHIVE_FILES and guess_type(file)[0] not in FILES_TO_PRESERVE:
            file = zip_file(file)
        # api restriction
        file_size = os.path.getsize(file)
        if file_size < MAX_FILE_SIZE:
            if file_size < space:
                yield file
            else:
                if LOGGER:
                    LOGGER.warning('The cloud has not enough space for <{}>. Left: {} (B). Required: {} (B).'.format(file, space, file_size))
                continue
        else:
            if LOGGER:
                LOGGER.warning('File {} is too large, omitting'.format(file))
            continue


def get_yes_no(value):
    """ coercing boolean value to 'yes' or 'no' """
    return 'yes' if value else 'no'


def create_cloud_path(path, cloud_base=CLOUD_PATH, local_base=UPLOAD_PATH):
    """ converts os path to the format acceptable by the cloud
    example:
    cloud_base='/backups'
    local_base='./upload'
    path='./upload\\level1_1'
    result='/backups/level1_1'
    """
    normalized_path = path.replace('\\', '/')
    clean_path = normalized_path.replace(local_base, '', 1)
    return cloud_base + clean_path


def resource_path(relative_path):
    """ Get absolute path to resource (source or frozen) """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)

    return os.path.join(os.path.abspath('.'), relative_path)


def close_logger(logger):
    handlers = logger.handlers[:]
    for handler in handlers:
        handler.close()
        logger.removeHandler(handler)


def main():
    # setting up global logger
    global LOGGER
    LOGGER = get_logger(__name__, log_file=LOG_FILE)
    if IS_FROZEN:
        # do not upload self, skip exe file with dependencies
        FILES_TO_SKIP.add(os.path.basename(sys.executable))
        # supplying ca certificate for https
        # cacert file should be in module's directory
        # for cx_Freeze
        #cacert = os.path.join(os.path.dirname(sys.executable), CACERT_FILE)
        # for PyInstaller
        cacert = resource_path(CACERT_FILE)
    else:
        # provide CA cert (not necessary)
        cacert = requests.certs.where()
        # do not upload self, skip module's file
        try:
            self_file = os.path.basename(os.path.abspath(sys.modules['__main__'].__file__))
        except:
            LOGGER.warning('Cannot get self file name.')
        else:
            FILES_TO_SKIP.add(self_file)
    assert os.path.isfile(cacert), 'Fatal Error. CA certificate not found.'
    os.environ["REQUESTS_CA_BUNDLE"] = cacert
    # some day this conditional mess should be replaced with class
    # cloud credentials should be in the configuration file
    if IS_CONFIG_PRESENT:
        # preparing to upload
        uploaded_files = set()
        with requests.Session() as s:
            cloud_csrf = get_cloud_csrf(s)
            if cloud_csrf:
                upload_domain = get_upload_domain(s, csrf=cloud_csrf)
                if upload_domain and os.path.isdir(UPLOAD_PATH):
                    for folder, __, __ in list(os.walk(UPLOAD_PATH)):
                        # cloud dir should exist before uploading
                        cloud_path = create_cloud_path(folder)
                        create_folder(s, folder=cloud_path, csrf=cloud_csrf)
                        # uploading files
                        for file in get_dir_files(path=folder, space=get_cloud_space(s, csrf=cloud_csrf)):
                            hash, size = post_file(s, domain=upload_domain, file=file)
                            if size and hash:
                                LOGGER.info('File {} successfully posted'.format(file))
                                cloud_file = cloud_path + '/' + os.path.basename(file)
                                if add_file(s, file=cloud_file, hash=hash, size=size, csrf=cloud_csrf):
                                    LOGGER.info('File {} successfully added'.format(file))
                                    uploaded_files.add(file)
                                else:
                                    LOGGER.error('File {} addition failed'.format(file))
                            else:
                                LOGGER.error('File {} post failed'.format(file))
                else:
                    LOGGER.error('Upload failed, check settings in <{}>'.format(CONFIG_FILE))
            else:
                LOGGER.error('Upload failed, check email credentials in <{}>'.format(CONFIG_FILE))
        uploaded_num = len(uploaded_files)
        LOGGER.info('{} file(s) successfully uploaded'.format(uploaded_num))
        if MOVE_UPLOADED:
            upload_dir = os.path.abspath(UPLOAD_PATH)
            uploaded_dir = os.path.abspath(UPLOADED_PATH)
            for file in uploaded_files:
                file_dir, file_name  = os.path.split(os.path.abspath(file))
                # pretty unreliable way to create path
                file_new_dir = file_dir.replace(upload_dir, uploaded_dir, 1)
                os.makedirs(file_new_dir, exist_ok=True)
                move(file, os.path.join(file_new_dir, file_name))
                LOGGER.info('file {} moved to {}'.format(file, file_new_dir))
        elif REMOVE_UPLOADED and uploaded_files:
            for file in uploaded_files:
                os.unlink(file)
                LOGGER.info('file {} removed'.format(file))
        if REMOVE_FOLDERS and (MOVE_UPLOADED or REMOVE_UPLOADED):
            for folder, __, __ in list(os.walk(UPLOAD_PATH, topdown=False)):
                if folder != UPLOAD_PATH and not os.listdir(folder):
                    os.rmdir(folder)
                    LOGGER.info('Empty directory {} deleted'.format(folder))
        print('{} file(s) uploaded. See {} for details.'.format(uploaded_num, LOG_FILE))
    else:
        # creating a default config if local configuration does not exists
        config['Credentials'] = {'Email': LOGIN, 'Password': PASSWORD}
        config['Locations'] = {'CloudPath': CLOUD_PATH, 'UploadPath': UPLOAD_PATH, 'UploadedPath': UPLOADED_PATH}
        config['Behaviour'] = {'ArchiveFiles': get_yes_no(ARCHIVE_FILES),
                               'MoveUploaded': get_yes_no(MOVE_UPLOADED),
                               'RemoveUploaded': get_yes_no(REMOVE_UPLOADED),
                               'RemoveFolders': get_yes_no(REMOVE_FOLDERS)}
        with open(CONFIG_FILE, mode='w') as f:
            config.write(f)
        LOGGER.warning('No configuration file () provided. Prepare it and run module again.'.format(CONFIG_FILE))
        print('Please, check out configuration file: <{}> and run me again'.format(CONFIG_FILE))
    LOGGER.info('###----------SESSION ENDED----------###')
    close_logger(LOGGER)


if __name__ == '__main__':
    main()
