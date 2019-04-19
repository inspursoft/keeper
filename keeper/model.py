# from collections import namedtuple
# User = namedtuple('User', ['user_id', 'username', 'token'])
# Project = namedtuple('Project', ['project_id', 'project_name'])
# VM = namedtuple('VM', ['vm_id', 'vm_name', 'target', 'keeper_url'])
# Snapshot = namedtuple('Snapshot', ['vm_id', 'snapshot_name'])
# Runner = namedtuple('Runner', ['runner_id', 'runner_tag'])

class User:
  __slots__ = 'user_id', 'username', 'token'
  def __init__(self, username, token):
    self.username = username
    self.token = token
 
  def __str__(self):
    return "user_id: %d, username: %s, token: %s" % (self.user_id, self.username, self.token)


class Project:
  __slots__ = 'project_id', 'project_name'
  def __init__(self, project_name):
    self.project_name = project_name
  
  def __str__(self):
    return "project_id: %d, project_name: %s" % (self.project_id, self.project_name)
  
class VM:
  __slots__ = 'vm_id', 'vm_name', 'target', 'keeper_url'
  def __init__(self, vm_id, vm_name, target, keeper_url):
    self.vm_id = vm_id
    self.vm_name = vm_name
    self.target = target
    self.keeper_url = keeper_url


class Snapshot:
  __slots__ = 'vm_id', 'snapshot_name'
  def __init__(self, vm_id, snapshot_name):
    self.vm_id = vm_id
    self.snapshot_name = snapshot_name


class Runner:
  __slots__ = 'runner_id', 'runner_tag'
  def __init__(self, runner_tag):
    self.runner_tag = runner_tag

  def __str__(self):
    return "runner_id: %s, runner_tag: %s" % (self.runner_id, self.runner_tag)