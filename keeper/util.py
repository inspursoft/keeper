from paramiko import SSHClient, AutoAddPolicy
from scp import SCPClient
from jinja2 import Environment, PackageLoader, Template
import os
from threading import Thread
from keeper import get_info
from keeper import db
from os import path
import time

class SSHUtil:
  @classmethod
  def _get_ssh_client(cls, custom_conf=None):
    cls.client = SSHClient()
    cls.client.set_missing_host_key_policy(AutoAddPolicy())
    hostname=get_info('HOST')
    username=get_info('USERNAME')
    password=get_info('PASSWORD')
    if custom_conf:
      hostname=custom_conf["HOST"]
      username=custom_conf["USERNAME"]
      password=custom_conf["PASSWORD"]
    cls.client.connect(hostname=hostname, username=username, password=password)
      
  @classmethod
  def exec_script(cls, app, filepath, *args, custom_conf=None):
    try:
      cls._get_ssh_client(custom_conf=custom_conf)
      app.logger.debug('{} {}'.format(filepath, ' '.join(args)))
      if custom_conf and "SCRIPT_PATH" in custom_conf:
        filepath = path.join(custom_conf["SCRIPT_PATH"], filepath)
      _, stdout, _ = cls.client.exec_command('{} {}'.format(filepath, ' '.join(args)))
      time.sleep(2)
      return stdout.read().decode("utf-8")
    except Exception as e:
      app.logger.error("Failed to execute script: %s with error: %s", "{} {}".format(filepath, *args), e)
    finally:
      if cls.client:
        cls.client.close()
 
  @classmethod
  def secure_copyfile(cls, app, src, dest):
    try:
      cls._get_ssh_client()
      with SCPClient(cls.client.get_transport()) as scp:
        scp.put(src, remote_path=dest)
    except Exception as e:
      app.logger.error("Failed to execute secure copyfile with error: %s", e)

  @classmethod
  def secure_copy(cls, app, src, dest):
    try:
      cls._get_ssh_client()
      with SCPClient(cls.client.get_transport()) as scp:
        for root, dirs, files in os.walk(src, topdown=True):
          for dir in dirs:
            scp.put(os.path.join(root, dir), remote_path=dest, recursive=True)
            for file in files:
              scp.put(os.path.join(root, file), remote_path=dest)
    except Exception as e:
      app.logger.error("Failed to execute secure copy with error: %s", e)

class TemplateUtil:
  @classmethod
  def _get_template(cls, template_name):
    env = Environment(loader=PackageLoader("keeper", "templates"))
    cls.template = env.get_template(template_name)

  @classmethod
  def render_file(cls, dest_path, template_name, kwargs):
    cls._get_template(template_name)
    try:
      os.makedirs(dest_path)
    except OSError:
      pass
    with open(os.path.join(dest_path, template_name), "w") as f:
      f.write(cls.template.render(kwargs))

  @classmethod
  def render_simple(cls, template, **kwargs):
    return Template(template).render(**kwargs)

class SubTaskUtil:

  @classmethod
  def set(cls, current_app, callback):
    cls.current = current_app._get_current_object()
    cls.callback = callback
    return cls

  @classmethod
  def subtask(cls):
    with cls.current.app_context():
      cls.callback()
    return cls
  
  @classmethod
  def start(cls):
    Thread(target=SubTaskUtil.subtask).start()

import time

class TaskCountUtil:
  counts = {}
  app = {}
  message = None
  canceled = False

  @classmethod
  def put(cls, id, initial, current):
    cls.app = current
    cls.message = None
    if id not in cls.counts:
      cls.counts[id] = initial
      cls.canceled = True
      cls.app.logger.debug("Put %s into TaskCount.", id)
      
  @classmethod
  def countdown(cls, id):
    while len(cls.counts.keys()) > 0:
      for id in list(cls.counts.keys()):
        if cls.canceled:
          cls.counts.pop(id)
          cls.app.logger.debug("Canceling countdown task for pipeline %s", id)
          return
        cls.app.logger.debug("Countdown task %s with %d in TaskCount", id, cls.counts[id])
        cls.counts[id] -= 1
        if cls.counts[id] == 0:
          cls.record(id)
          cls.counts.pop(id)
        time.sleep(1)
      time.sleep(1)
  
  @classmethod
  def record(cls, message):
    cls.message = message
    cls.app.logger.debug("Reported task %s in TaskCount as it has reached.", cls.message)

  @classmethod
  def report(cls):
    return cls.message