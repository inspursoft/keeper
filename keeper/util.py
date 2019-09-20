from paramiko import SSHClient, AutoAddPolicy
from scp import SCPClient
from jinja2 import Environment, PackageLoader, Template
import os
from threading import Thread
from keeper import get_info
from keeper import db

class SSHUtil:
  @classmethod
  def _get_ssh_client(cls):
    cls.client = SSHClient()
    cls.client.set_missing_host_key_policy(AutoAddPolicy())
    cls.client.connect(hostname=get_info('HOST'), username=get_info('USERNAME'), password=get_info('PASSWORD'))
  
  @classmethod
  def exec_script(cls, app, filepath, *args):
    try:
      cls._get_ssh_client()
      app.logger.debug('{} {}'.format(filepath, ' '.join(args)))
      _, stdout, _ = cls.client.exec_command('{} {}'.format(filepath, ' '.join(args)))
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