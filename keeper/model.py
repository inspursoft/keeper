# from collections import namedtuple
# User = namedtuple('User', ['user_id', 'username', 'token'])
# Project = namedtuple('Project', ['project_id', 'project_name'])
# VM = namedtuple('VM', ['vm_id', 'vm_name', 'target', 'keeper_url'])
# Snapshot = namedtuple('Snapshot', ['vm_id', 'snapshot_name'])
# Runner = namedtuple('Runner', ['runner_id', 'runner_tag'])
import re

class User:
  __slots__ = 'user_id', 'username', 'token'
  def __init__(self, user_id, username, token):
    self.user_id = user_id
    self.username = username
    self.token = token

  def __str__(self):
    return "user_id: %d, username: %s, token: %s" % (self.user_id, self.username, self.token)
  
  @classmethod
  def new(cls):
    return cls(0, '', '')


class Project:
  __slots__ = 'project_id', 'project_name', 'runner_token', 'priority'
  def __init__(self, project_name):
    self.project_name = project_name
    self.priority = -1
  
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
  __slots__ = 'runner_id', 'runner_name'
  def __init__(self, runner_name):
    self.runner_name = runner_name

  def __str__(self):
    return "runner_id: %s, runner_name: %s" % (self.runner_id, self.runner_name)

class NoteTemplate:
  __slots__ = 'name', "content"
  def __init__(self, name, content):
    self.name = name
    self.content = content
    
  def __str__(self):
    return "template name: %s, content: %s" % (self.name, self.content)

class VMGlobalStatus:
  __slots__ = "id", "name", "provider", "status", "directory"
  @classmethod
  def parse(cls, raw_content, name):
    p = re.compile(r'''
      (?![\-]+\n)
      (?P<id>\w{7})\s+
      (?P<name>\w+)\s+
      (?P<provider>\w+)\s+
      (?P<status>\w+)\s+
      (?P<directory>[\w/-]+)\s+
      (?=\n)''',re.VERBOSE)
    try:
      for m in p.finditer(raw_content):
        vm_global_status = VMGlobalStatus()
        vm_global_status.id = m.group("id")
        vm_global_status.name = m.group("name")
        vm_global_status.provider = m.group("provider")
        vm_global_status.status = m.group("status")
        vm_global_status.directory = m.group("directory")
        vm_name = vm_global_status.directory[vm_global_status.directory.rindex("/")+1:]
        if vm_name == name:
          return vm_global_status
    except Exception:
      pass
    return None

  def __str__(self):
    return "id: {}, name: {}, provider: {}, status: {}, directory: {}".format(
      self.id, self.name, self.provider, self.status, self.directory)

class VMConf:
  __slots__= "gitlab_url", "vm_box", "vm_memory", "vm_ip", "runner_name", "runner_tag", "runner_token"

class ProjectRunner:
  __slots__= "project_id", "runner_id"
    
  def __init__(self, project_id, runner_id):
    self.project_id = project_id
    self.runner_id = runner_id
    
  def __str__(self):
    return "Project runner - project ID: %d, runner ID: %d" % (self.project_id, self.runner_id)

class IPProvision:
  __slots__ = "id", "ip_address"
  
  def __init__(self, id, ip_address):
    self.id = id
    self.ip_address = ip_address
  
  def __str__(self):
    return "IP provision - ID: %d, IP address: %s" % (self.id, self.ip_address)

class PipelineTask:
  __slots__ = "id", "priority"

  def __init__(self, id, priority):
    self.id = id
    self.priority = priority

  def __lt__(self, other):
    return self.priority < other.priority

  def __gt__(self, other):
    return self.priority > other.priority

  def __eq__(self, other):
    return self.priority == other.priority
