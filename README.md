# mail.ru-uploader
Unofficial mail.ru cloud file uploader. Check official license agreement first (https://cloud.mail.ru/LA/). 

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.
This project has been created to accomplish just one and very small internal goal - upload bunch of files to the Mail.ru Cloud storage from time to time.

### Prerequisities

To run the uploader from source you need to install:

Python 3.3+ (2.7+ might be enough as well)
with modules:
```
pip install requests requests-toolbelt
```

On Windows systems (Windows 7 and above) you could also use pre-built version of the uploader.
Just install the following prerequisities: [Visual C++ Redistributable for Visual Studio 2015](https://www.microsoft.com/en-us/download/details.aspx?id=48145).
Then run the executable (mail.ru-uploader.exe) by double-click or from the command line.

Please make sure that your have read/write permissions to the module's root folder, the upload/uploaded folders and the cloud

### Installing and Using

No installation is necessary.
Just download an 'upload.py' file to the place where your directory with files to upload is and than run the uploader from shell:
```
python -m upload
```
The very first run will create '.config' settings file with a few pretty descriptive options.
You should fill out them before next run, which is actually will upload your files to the cloud if settings are correct.
Please make sure that you have provided correct full email address and password for your Mail.ru cloud account in 'Credentials' section.
The uploader will not send them to any third parties. But it will keep it on your local storage in plain text.
Also you should have a folder with the files to upload in module's directory.
This folder should be named after an 'UploadPath' configuration option value, by default it is 'upload'.

You can add this command to Cron, Windows Task Scheduler or other similar job scheduler in your OS if you like. Do not forget to use module's full path though.
Configuration and log files will be always created in the directory you execute your command, which is not necesary the directory where the uploader executable is situated. It means that you can have as many different running configurations as you like with single uploader executable. You should specify executable's working directory in the scheduler's task in this case.

Be aware that the cloud uses its own archiving system. Which means that when later you download your files from it they could be zipped twice.

## Running the tests (coverage: 70%)
Install pytest in your virtual environment if not installed:
```
pip install pytest
```

To run tests from shell use:
```
py.test
```

Provide email credentials if configuration file is not ok:
```
py.test --email=your_email@mail.ru --password=your_password
```

Pass --runweb option to run cloud related tests
```
py.test --runweb
```

Pass --rundirty option to run cloud related tests which will leave some data in the cloud's recycle bin
```
py.test --rundirty
```

## License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details
