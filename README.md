# mail.ru-uploader
Unofficial mail.ru cloud file uploader. Check official license agreement first (https://cloud.mail.ru/LA/). 

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.
This project has been created to accomplish just one and very small internal goal - upload bunch of files to the Mail.ru Cloud storage from time to time.

### Prerequisities

Things you need to install the software and how to install them:

Python 3.3+ (2.7+ might be enough as well)
with modules:
```
pip install requests requests-toolbelt
```

### Installing and Using

No installation is necessary.
Just download 'upload.py' file to the directory you want to upload files from, fill up 'SET AS YOU NEED PARAMETERS' block in it, which has a couple descriptive enough variables necessary to set according to your local environment and cloud account, and than run uploader from shell:
```
python -m upload
```
You can add this command to Cron, Windows Task Scheduler or other similar job scheduler in your OS if you like. Do not forget to use module's full path though.

## Running the tests
no tests added yet :-(

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details
