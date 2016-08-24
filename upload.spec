# -*- mode: python -*-
"""
Created: 2016-11-08

@author: pymancer

windows executable PyInstaller builder config

usage:
pyinstaller --one-file upload.spec
"""
import requests

cacert = requests.certs.where()

block_cipher = None


a = Analysis(['upload.py'],
             pathex=['.'],
             binaries=None,
             datas=None,
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)
a.datas.append(('cacert.pem', cacert, 'DATA'))
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name=os.path.join('dist', 'mail.ru-uploader'),
          debug=False,
          strip=False,
          upx=True,
          console=True )
