#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
Created: 2016-08-09

@author: pymancer

uploads specified directory contents to mail.ru cloud
- ONLY plain text and zip files TESTED, no contents checking though, only extensions
- same name files in the cloud will not be replaced (still posted though)
- NO linux hidden files upload (names starting with dot)

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
import pprint
import logging
import os.path
import zipfile
import requests
import datetime
import configparser
from mimetypes import guess_type
from requests_toolbelt import MultipartEncoder
from requests.compat import urljoin, quote_plus
from logging.handlers import RotatingFileHandler

__version__ = '0.0.2'

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
# relative to cloud root, must end with slash, create this folder in the cloud before using this module
CLOUD_PATH = config.get('Locations', 'CloudPath', fallback='backups/')
# local folder path with files to upload, use '.' to set path relative to the module location
UPLOAD_PATH = config.get('Locations', 'UploadPath', fallback='./upload')
# local folder to move uploaded files, will be created if not exists
UPLOADED_PATH = config.get('Locations', 'UploadedPath', fallback='./uploaded')
# True, if False - no uploaded files zipping
ARCHIVE_FILES = config.getboolean('Behaviour', 'ArchiveFiles', fallback=True)
# True, if False - old files should be deleted manually before next session
REMOVE_UPLOADED = config.getboolean('Behaviour', 'RemoveUploaded', fallback=True)
# False, if True uploaded files will be moved to UPLOADED_PATH directory, REMOVE_UPLOADED setting will be ignored
MOVE_UPLOADED = config.getboolean('Behaviour', 'MoveUploaded', fallback=True)
###--------------------------------------###

LOG_PATH  = './upload.log' # log file path relative to the module location (please, include file name)
CLOUD_URL = 'https://cloud.mail.ru/api/v2/'
VERIFY_SSL = True # True, use False only for debug and if you know what you're doing
CLOUD_DOMAIN_ORD = 2 # 2 - practice, 1 - theory
API_VER = 2 # 2 - constant so far
TIME_AMEND = '0246' # '0246', exact meaning has not been quite sorted out yet
CLOUD_CONFLICT = 'strict' # 'strict' - should remain unchanged at least until 'rename' implementation
MAX_FILE_SIZE = 2*1024*1024*1024 # 2*1024*1024*1024 (bytes ~ 2 GB), API constraint
FILES_TO_PRESERVE = ('application/zip', ) # do not archive already zipped files
QUOTED_LOGIN = quote_plus(LOGIN) # just for convenience
DEFAULT_FILETYPE = 'text/plain' # 'text/plain' is good option
# do not upload this files (only for module's directory)
FILES_TO_SKIP = set((os.path.basename(CONFIG_FILE), os.path.basename(LOG_PATH)))
CACERT_FILE = 'cacert.pem'

# logger setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# create a file handler
handler = RotatingFileHandler(LOG_PATH, mode='a', maxBytes=5*1024*1024, backupCount=2, encoding=None, delay=0)
handler.setLevel(logging.INFO)
# create a logging format
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(handler)


def cloud_auth(session, login=LOGIN, password=PASSWORD):
    r = session.post('https://auth.mail.ru/cgi-bin/auth?lang=ru_RU&from=authpopup',
                     data = {'Login': LOGIN, 'Password': PASSWORD, 'page': urljoin(CLOUD_URL, '?from=promo'),
                             'new_auth_form': 1, 'Domain': LOGIN.split('@')[1]}, verify = VERIFY_SSL)
    if r.status_code == requests.codes.ok:
        return True
    else:
        logger.error('Mail authorization request unsuccessful, http code: {}, msg: {}'.format(r.status_code, r.text))
    return None


def get_csrf(session):
    r = session.get(urljoin(CLOUD_URL, 'tokens/csrf'), verify = VERIFY_SSL)
    if r.status_code == requests.codes.ok:
        r_json = r.json()
        return r_json['body']['token']
    else:
        logger.error('CSRF token request unsuccessful, http code: {}, msg: {}'.format(r.status_code, r.text))
    return None


def get_upload_domain(session, csrf=''):
    url = urljoin(CLOUD_URL, 'dispatcher?token=' + csrf)
    r = session.get(url, verify = VERIFY_SSL)
    if r.status_code == requests.codes.ok:
        r_json = r.json()
        return r_json['body']['upload'][0]['url']
    else:
        logger.error('Upload domain request unsuccessful, http code: {}, msg: {}'.format(r.status_code, r.text))
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

def post_file(session, domain='', filename='', filetype=''):
    assert domain is not None, 'No upload domain provided'
    assert filename is not None, 'No file to upload provided'

    if not filetype:
        logger.warning('No file type provided, using default: {}'.format(DEFAULT_FILETYPE))
        filetype = DEFAULT_FILETYPE

    timestamp = str(int(time.mktime(datetime.datetime.now().timetuple()))) + TIME_AMEND
    url = urljoin(domain, '?cloud_domain=' + str(CLOUD_DOMAIN_ORD) + '&x-email=' + QUOTED_LOGIN + '&fileapi' + timestamp)
    m = MultipartEncoder(fields={'file': (quote_plus(filename), open(os.path.join(UPLOAD_PATH, filename), 'rb'), filetype)})

    r = session.post(url, data=m, headers={'Content-Type': m.content_type}, verify = VERIFY_SSL)
    if r.status_code == requests.codes.ok:
        if len(r.content):
            hash = r.content[:40].decode()
            size = int(r.content[41:-2])
            return (hash, size)
        else:
            logger.error('File {} post error, no hash and size obtained'.format(filename))
    else:
        logger.error('File {} post error, http code: {}, msg: {}'.format(filename, r.status_code, r.text))
    return (None, None)


def add_file(session, filename='', hash='', size=0, csrf=''):
    assert filename is not None, 'No file to upload passed'
    assert hash is not None, 'No hash passed'
    assert size is not None, 'No size passed'
    assert csrf is not None, 'No CSRF token passed'

    url = urljoin(CLOUD_URL, 'file/add')
    # api, email, x-email, x-page-id (not implemented), build (not implemented) - optional parameters
    postdata = {'home': CLOUD_PATH + filename, 'hash': hash, 'size': size, 'conflict': CLOUD_CONFLICT, 'token': csrf,
                'api': API_VER, 'email':LOGIN, 'x-email': LOGIN}

    r = s.post(url, data=postdata, headers={'Content-Type': 'application/x-www-form-urlencoded'}, verify=VERIFY_SSL)
    if r.status_code == requests.codes.ok:
        return True
    else:
        logger.error('File {} addition error, http code: {}, msg: {}'.format(filename, r.status_code, r.text))
    return None


def zip_file(file):
    """ creates compressed zip files with same name and 'zip' extension
    on success deletes original file
    on failure returns original file name
    replaces existing archives
    """
    file_root, file_ext = os.path.splitext(file)
    zip_name = file_root + '.zip'
    compression = zipfile.ZIP_DEFLATED
    try:
        zf = zipfile.ZipFile(os.path.join(UPLOAD_PATH, zip_name), mode='w')
        zf.debug = 0
        # convert unicode file names to byte strings if any
        zf.write(os.path.join(UPLOAD_PATH, file), arcname=file, compress_type=compression)
    except Exception as e:
        logger.error('Failed to archive {}, error:'.format(file, e))
        zip_name = file
    else:
        os.unlink(os.path.join(UPLOAD_PATH, file))
    finally:
        zf.close()
    return zip_name


def get_dir_files(path=UPLOAD_PATH, space=0):
    """ returns list of the cwd files, follows cloud restrictions """
    assert space is not None, 'No cloud space left or space fetching error'

    for file in next(os.walk(UPLOAD_PATH))[2]:
        # in case we uploading current directory
        if file in FILES_TO_SKIP and UPLOAD_PATH == '.':
            continue
        # in case some files are already zipped
        if ARCHIVE_FILES and guess_type(file)[0] not in FILES_TO_PRESERVE:
            file = zip_file(file)
        # api restriction
        file_size = os.path.getsize(os.path.join(path,file))
        if file_size < MAX_FILE_SIZE:
            if file_size < space:
                yield file
            else:
                logger.warning('The cloud has not enough space for <{}>. Left: {} (B). Required: {} (B).'.format(file, space, file_size))
                continue
        else:
            logger.warning('File {} is too large, omitting'.format(file))
            continue


def get_yes_no(value):
    """ helper function
    coercing boolean value to 'yes' or 'no'
    """
    return 'yes' if value else 'no'


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)

    return os.path.join(os.path.abspath('.'), relative_path)


if __name__ == '__main__':
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
            logger.warning('Cannot get self file name.')
        else:
            FILES_TO_SKIP.add(self_file)
    assert os.path.isfile(cacert), 'Fatal Error. CA certificate not found.'
    os.environ["REQUESTS_CA_BUNDLE"] = cacert
    # cloud credentials should be in the configuration file
    if IS_CONFIG_PRESENT:
        # uploading files
        uploaded_files = set()
        with requests.Session() as s:
            cloud_csrf = get_cloud_csrf(s)
            if cloud_csrf:
                upload_domain = get_upload_domain(s, csrf=cloud_csrf)
                if upload_domain and os.path.isdir(UPLOAD_PATH):
                    for file in get_dir_files(space=get_cloud_space(s, csrf=cloud_csrf)):
                        hash, size = post_file(s, domain=upload_domain, filename=file, filetype=guess_type(file)[0])
                        if size and hash:
                            logger.info('File {} successfully posted'.format(file))
                            if add_file(s, filename=file, hash=hash, size=size, csrf=cloud_csrf):
                                logger.info('File {} successfully added'.format(file))
                                uploaded_files.add(file)
                            else:
                                logger.error('File {} addition failed'.format(file))
                        else:
                            logger.error('File {} post failed'.format(file))
                else:
                    logger.error('Upload failed, check settings in <{}>'.format(CONFIG_FILE))
            else:
                logger.error('Upload failed, check email credentials in <{}>'.format(CONFIG_FILE))
        uploaded_num = len(uploaded_files)
        logger.info('{} file(s) successfully uploaded'.format(uploaded_num))
        if MOVE_UPLOADED:
            if not os.path.exists(UPLOADED_PATH):
                os.makedirs(UPLOADED_PATH)
            for file in uploaded_files:
                os.rename(os.path.join(UPLOAD_PATH, file), os.path.join(UPLOADED_PATH, file))
        elif REMOVE_UPLOADED and uploaded_files:
            for file in uploaded_files:
                os.unlink(os.path.join(UPLOAD_PATH, file))
        print('{} file(s) uploaded. See {} for details.'.format(uploaded_num, LOG_PATH))
    else:
        # creating a default config if local configuration does not exists
        config['Credentials'] = {'Email': LOGIN, 'Password': PASSWORD}
        config['Locations'] = {'CloudPath': CLOUD_PATH, 'UploadPath': UPLOAD_PATH, 'UploadedPath': UPLOADED_PATH}
        config['Behaviour'] = {'ArchiveFiles': get_yes_no(ARCHIVE_FILES), 'RemoveUploaded': get_yes_no(REMOVE_UPLOADED)}
        with open(CONFIG_FILE, mode='w') as f:
            config.write(f)
        logger.warning('No configuration file () provided. Prepare it and run module again.'.format(CONFIG_FILE))
        print('Please, check out configuration file: <{}> and run me again'.format(CONFIG_FILE))
    logger.info('###----------SESSION ENDED----------###')

