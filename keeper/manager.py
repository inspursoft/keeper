from . import get_info
import keeper.db as db

import requests

from keeper.model import *

class KeeperException(Exception):
  pass

class KeeperManager:
  
  def __init__(self, current, vm_name):
    self.current = current
    self.vm_name = vm_name

  def get_token(self):
    if 'token' in dict(self.get_vm_with_runner()):
      return self.get_vm_with_runner()['token']
    return None

  def get_vm_with_runner(self):
    r = db.get_project_runner(self.vm_name) 
    if r is None:
      r = db.get_vm_snapshot(self.vm_name) 
      if r is None:
        raise KeeperException('Cannot get runner ID with project: %s' % self.vm_name)
    return r

  def get_runner_id(self):
    if 'runner_id' in dict(self.get_vm_with_runner()):
      return self.get_vm_with_runner()['runner_id']
    return None

  def get_keeper_url(self):
    return self.get_vm_with_runner()['keeper_url']

  def get_vm_snapshot_name(self, vm_name):
    return db.get_vm_snapshot(vm_name)['snapshot_name']

  def toggle_runner(self, status):
    request_url = "%s/runners/%d?private_token=%s" % (get_info('GITLAB_API_PREFIX'), self.get_runner_id(), self.get_token())
    resp = requests.put(request_url, data={'active': status})
    self.current.logger.debug("Requested URL: %s to toggle runner status as %s", request_url, status)
    if resp.status_code >= 400:
      raise KeeperException('Failed to request with URL: %s' % request_url)


  def dispatch_task(self, dispatch_url):
    resp = requests.get(dispatch_url)
    self.current.logger.debug("Requested URL: %s with status: %d", dispatch_url, resp.status_code)
    if resp.status_code >= 400:
      raise KeeperException('Failed to request with URL: %s' % dispatch_url)


  @staticmethod
  def add_vm_snapshot(vm, snapshot, app):
    r = db.check_vm_snapshot(vm, snapshot, app)
    if r['cnt'] == 0:
      db.insert_vm(vm, app)
      db.insert_snapshot(snapshot, app)
    else:
      app.logger.error("VM: %s with snapshot: %s already exists." % (vm.vm_name, snapshot.snapshot_name))
      raise KeeperException("VM: %s with snapshot: %s already exists." % (vm.vm_name, snapshot.snapshot_name))


  @staticmethod
  def get_gitlab_users(token, app):
    request_url = "%s/users?private_token=%s" % (get_info('GITLAB_API_PREFIX'), token)
    resp = requests.get(request_url)
    if resp.status_code >= 400:
      app.logger.error("Failed to request URL: %s with status code: %d", request_url, resp.status_code)
      raise KeeperException("Failed to request URL: %s with status code: %d" % (request_url, resp.status_code))
    return resp.json()


  @staticmethod
  def get_gitlab_projects(token, app):
    request_url = "%s/projects?private_token=%s" % (get_info('GITLAB_API_PREFIX'), token)
    resp = requests.get(request_url)
    if resp.status_code >= 400:
      app.logger.error("Failed to request URL: %s with status code: %d", request_url, resp.status_code)
      raise KeeperException("Failed to request URL: %s with status code: %d" % (request_url, resp.status_code))
    return resp.json()


  @staticmethod
  def get_gitlab_runners(project, token, app):
    request_url = "%s/projects/%d/runners?private_token=%s" % (get_info('GITLAB_API_PREFIX'), project.project_id, token)
    resp = requests.get(request_url)
    if resp.status_code >= 400:
      app.logger.error("Failed to request URL: %s with status code: %d", request_url, resp.status_code)
      raise KeeperException("Failed to request URL: %s with status code: %d" % (request_url, resp.status_code))
    return resp.json()


  @staticmethod
  def get_repo_commit_status(project_id, commit_id, token, app):
    request_url = "%s/projects/%d/repository/commits/%s/statuses?private_token=%s" % (get_info('GITLAB_API_PREFIX'), project_id, commit_id, token)
    resp = requests.get(request_url)
    if resp.status_code >= 400:
      app.logger.error("Failed to request URL: %s with status code: %d", request_url, resp.status_code)
      raise KeeperException("Failed to request URL: %s with status code: %d" % (request_url, resp.status_code))
    return resp.json()


  @staticmethod
  def trigger_pipeline(project_id, ref, app):
    r = db.get_user_token_by_project(project_id)
    request_url = "%s/projects/%d/pipeline?ref=%s" % (get_info('GITLAB_API_PREFIX'), project_id, ref)
    resp = requests.post(request_url, headers={"PRIVATE-TOKEN": r['token']})
    if resp.status_code >= 400:
      app.logger.error("Failed to request URL: %s with status code: %d", request_url, resp.status_code)
      raise KeeperException("Failed to request URL: %s with status code: %d" % (request_url, resp.status_code))
    return resp.json()

  
  @staticmethod
  def resolve_token(username, app):
    r = db.get_user_token(username)
    if r is None:
      app.logger.error("User: %s does not exists." % username)
      raise KeeperException("User: %s does not exists." % username)
    return r['token']


  @staticmethod
  def resolve_project(username, project_name, token, app):
    projects = KeeperManager.get_gitlab_projects(token, app)
    project = Project(project_name)
    found = False
    for p in projects:
      if p['path_with_namespace'] == project_name:
        project.project_id = p['id']
        found = True
        break
    if not found:
      raise KeeperException("No project id found with provided project name: %s" % project_name)
    app.logger.debug("Obtained project: %s in project runner registration." % project)    
    return project


  @staticmethod
  def register_project_runner(username, project_name, runner_name, vm, snapshot, token, app):
    project = KeeperManager.resolve_project(username, project_name, token, app)
    runners = KeeperManager.get_gitlab_runners(project, token, app)
    runner = Runner(runner_name)
    found = False
    for e in runners:
      if e['description'] == runner_name:
        runner.runner_id = e['id']
        found = True
        break
    if not found:
      raise KeeperException("No runner id found with provided tag: %s" % runner_name)
    app.logger.debug("Obtained runner: %s in project runner registration." % runner)    
    
    r = db.check_project_runner(project_name, vm.vm_name, runner.runner_id, snapshot.snapshot_name, app)
    if r['cnt'] == 0:
      db.insert_runner(runner, app)
      db.insert_project_runner(project, vm, runner, app)
      db.insert_vm(vm, app)
      db.insert_snapshot(snapshot, app)
    else:
      app.logger.error("Project: %s with runner: %s, VM: %s and snapshot: %s already exists."
         % (project.project_name, runner.runner_id, vm.vm_name, snapshot.snapshot_name))
      raise KeeperException("Project: %s with runner: %s, VM: %s and snapshot: %s already exists."
         % (project.project_name, runner.runner_id, vm.vm_name, snapshot.snapshot_name))


  @staticmethod
  def unregister_runner_by_name(runner_name, app):
    rs = db.get_project_runner_by_name(runner_name)
    if len(rs) == 0:
      app.logger.error("Runner name: %s does not exist." % runner_name)
    for r in rs:
      db.delete_project_runner(r['project_id'], r['runner_id'], app)
      db.delete_runner(r['runner_id'], app)
      db.delete_vm(r['vm_id'], app)
      db.delete_snapshot(r['snapshot_name'], app)


  @staticmethod
  def add_user_project(username, token, project_name, app):
    users = KeeperManager.get_gitlab_users(token, app)
    user = User(username, token)
    found = False
    for u in users:
      if u['username'] == username:
        user.user_id = u['id']
        found = True
        break
    if not found:
      raise KeeperException("No user id found with provided username: %s" % username)
    project = KeeperManager.resolve_project(username, project_name, token, app)
    app.logger.debug("Obtained project: %s in user creation with project." % project)    
    r = db.check_user_project(user.username, project.project_name, app)
    if r['cnt'] == 0:
      app.logger.debug("user: %s" % user)
      app.logger.debug("project: %s" % project)
      db.insert_user(user, app)
      db.insert_project(project, app)
      db.insert_user_project(user, project, app)
    else:
      app.logger.error("User: %s with project: %s already exists." % (user.username, project.project_name))
      raise KeeperException("User: %s with project: %s already exists." % (user.username, project.project_name))
    
    