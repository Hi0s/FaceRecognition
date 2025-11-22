#Use the code below in command line to kill currently used port
#lsof -i TCP:8000 | grep LISTEN  
#It might show like this:
#python3.1 39537 khanh    3u  IPv4 0xb071b9347ee9fa20      0t0  TCP *:irdmi (LISTEN)
#kill -9 39537

#Run server - first cd to django folder
#python manage.py runserver 0.0.0.0:8000

#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'FaceCheckin.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
