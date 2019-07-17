from . import get_info
import keeper.db as db

import requests
from requests.auth import HTTPBasicAuth

from keeper.model import *

import re

class KeeperException(Exception):
  def __init__(self, code, message):
    self.code = code
    self.message = message

  def __str__(self):
    return "Exception: {} with code: {}".format(self.message, self.code)

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
        raise KeeperException(404, 'Cannot get runner ID with project: %s' % self.vm_name)
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
      raise KeeperException(resp.status_code, 'Failed to request with URL: %s' % request_url)


  def dispatch_task(self, dispatch_url):
    resp = requests.get(dispatch_url)
    self.current.logger.debug("Requested URL: %s with status: %d", dispatch_url, resp.status_code)
    if resp.status_code >= 400:
      raise KeeperException(resp.status_code, 'Failed to request with URL: %s' % dispatch_url)


  @staticmethod
  def add_vm_snapshot(vm, snapshot, app):
    r = db.check_vm_snapshot(vm, snapshot, app)
    if r['cnt'] == 0:
      db.insert_vm(vm, app)
      db.insert_snapshot(snapshot, app)
    else:
      app.logger.error("VM: %s with snapshot: %s already exists." % (vm.vm_name, snapshot.snapshot_name))
      raise KeeperException(409, "VM: %s with snapshot: %s already exists." % (vm.vm_name, snapshot.snapshot_name))


  @staticmethod
  def get_gitlab_user(username, token, app):
    request_url = "%s/users?username=%s&private_token=%s" % (get_info('GITLAB_API_PREFIX'), username, token)
    resp = requests.get(request_url)
    if resp.status_code >= 400:
      app.logger.error("Failed to request URL: %s with status code: %d", request_url, resp.status_code)
      raise KeeperException(resp.status_code, "Failed to request URL: %s with status code: %d" % (request_url, resp.status_code))
    return resp.json()

  @staticmethod
  def get_gitlab_projects(token, app):
    request_url = "%s/projects?private_token=%s" % (get_info('GITLAB_API_PREFIX'), token)
    resp = requests.get(request_url)
    if resp.status_code >= 400:
      app.logger.error("Failed to request URL: %s with status code: %d", request_url, resp.status_code)
      raise KeeperException(resp.status_code, "Failed to request URL: %s with status code: %d" % (request_url, resp.status_code))
    return resp.json()

  @staticmethod
  def get_gitlab_runners(project_id, app):
    app.logger.debug("Get gitlab runner with project ID: %d", project_id)
    request_url = "%s/projects/%d/runners" % (get_info('GITLAB_API_PREFIX'), project_id)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, method='GET')

  @staticmethod
  def get_repo_commit_status(project_id, commit_id, app):
    app.logger.debug("Get repo with project ID: %d and commit ID: %d", project_id, commit_id)
    request_url = "%s/projects/%d/repository/commits/%s/statuses" % (get_info('GITLAB_API_PREFIX'), project_id, commit_id)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, method='GET')

  @staticmethod
  def request_gitlab_api(project_id, request_url, app, method='POST', params={}):
    r = db.get_user_token_by_project(project_id)
    if r is None:
      app.logger.error("Failed to get token with project ID: %d", project_id)
      raise KeeperException(404, "Failed to get token with project ID: %d" % (project_id,))
    app.logger.debug("Got token: %s", r['token'])
    resp = {}
    default_headers={"PRIVATE-TOKEN": r['token']}
    if method == 'POST':
      resp = requests.post(request_url, headers=default_headers, params=params)
    elif method == 'GET':
      resp = requests.get(request_url, headers=default_headers, params=params)
    elif method == 'PUT':
      resp = requests.put(request_url, headers=default_headers, params=params)
    if resp.status_code >= 400:
      app.logger.error("Failed to request URL: %s with status code: %d with content: %s", request_url, resp.status_code, resp.content)
      raise KeeperException(resp.status_code, "Failed to request URL: %s with status code: %d with content: %s" % (request_url, resp.status_code, resp.content))
    return resp.json()

  @staticmethod
  def request_sonarqube_api(sonarqube_token, request_url, app):
    app.logger.debug("Got Sonarqube token: %s", sonarqube_token)
    resp = requests.get(request_url, auth=HTTPBasicAuth(sonarqube_token,""))
    if resp.status_code >= 400:
      app.logger.error("Failed to request URL: %s with status code: %d with content: %s", request_url, resp.status_code, resp.content)
      raise KeeperException(resp.status_code, "Failed to request URL: %s with status code: %d with content: %s" % (request_url, resp.status_code, resp.content))
    return resp.json()

  @staticmethod
  def search_sonarqube_issues(sonarqube_token, sonarqube_project_name, app):
    app.logger.debug("Request Sonarqube issues for project: %s", sonarqube_project_name)
    request_url = "%s/issues/search?componentKeys=%s&severities=CRITICAL&createdInLast=10d" % (get_info('SONARQUBE_API_PREFIX'), sonarqube_project_name)
    return KeeperManager.request_sonarqube_api(sonarqube_token, request_url, app)

  @staticmethod
  def trigger_pipeline(project_id, ref, app):
    app.logger.debug("Trigger pipeline with project_id: %d", project_id)
    request_url = "%s/projects/%d/pipeline?ref=%s" % (get_info('GITLAB_API_PREFIX'), project_id, ref)
    return KeeperManager.request_gitlab_api(project_id, request_url, app)

  @staticmethod
  def create_branch(project_id, branch_name, ref, app):
    app.logger.debug("Create branch: %s from %s with project_id: %d", branch_name, ref, project_id)
    request_url = "%s/projects/%d/repository/branches?branch=%s&ref=%s" % (get_info('GITLAB_API_PREFIX'), project_id, branch_name, ref)
    return KeeperManager.request_gitlab_api(project_id, request_url, app)

  @staticmethod
  def create_branch_per_assignee(project_name, assignee_id, branch_name, ref, app):
    r = db.get_project_by_user_id(project_name, assignee_id)
    if r is None:
      app.logger.error("Failed to get project by assignee ID: %d", assignee_id)
      raise KeeperException(404, "Failed to get project by assignee ID: %s" % (assignee_id,))
    assignee = r['username']
    target_project_id = r['project_id']
    app.logger.debug("Create branch: %s per assignee: %s to project: %s", branch_name, assignee, project_name)
    try:
      KeeperManager.get_branch(target_project_id, branch_name, app)
    except KeeperException as e:
      app.logger.error("Branch: %s already exist to project: %s for assignee: %s ", branch_name, project_name, assignee)
    return KeeperManager.create_branch(target_project_id, branch_name, ref, app)

  @staticmethod
  def get_branch(project_id, branch_name, app):
    app.logger.debug("Get branch with project ID: %d", project_id)
    request_url = "%s/projects/%d/repository/branches/%s" % (get_info('GITLAB_API_PREFIX'), project_id, branch_name)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, method='GET')

  @staticmethod
  def comment_on_issue(project_id, issue_iid, message, app):
    app.logger.debug("Comment on issue to project ID: %d on issue IID: %d, with message: %s", project_id, issue_iid, message)
    request_url = "%s/projects/%d/issues/%d/notes?body=%s" % (get_info('GITLAB_API_PREFIX'), project_id, issue_iid, message)
    return KeeperManager.request_gitlab_api(project_id, request_url, app)

  @staticmethod
  def post_issue_to_assignee(project_id, title, description, label, assignee, app):
    app.logger.debug("Post issue to project ID: %d with title: %s, label: %s, description: %s ", project_id, title, description, label)
    r = KeeperManager.resolve_user(assignee, app)
    request_url = "%s/projects/%d/issues?title=%s&description=%s&labels=%s&assignee_ids=%d" % (get_info('GITLAB_API_PREFIX'), project_id, title, description, label, r['user_id'])
    return KeeperManager.request_gitlab_api(project_id, request_url, app)

  @staticmethod
  def update_issue(project_id, issue_iid, updates, app):
    app.logger.debug("Update issue to project ID: %d to issue IID: %d with changes: %s", project_id, issue_iid, updates)
    request_url = "%s/projects/%d/issues/%d" % (get_info('GITLAB_API_PREFIX'), project_id, issue_iid)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, method="PUT", params=updates)

  @staticmethod
  def get_milestone(project_id, milestone_id, app):
    app.logger.debug("Get milestone with project ID: %d with milestone ID: %d")
    request_url = "%s/projects/%d/milestones/%d" % (get_info('GITLAB_API_PREFIX'), project_id, milestone_id)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, method='GET')

  @staticmethod
  def get_all_milestones(project_id, params, app):
    app.logger.debug("Get all milestones with project ID: %d", project_id)
    request_url = "%s/projects/%d/milestones" % (get_info('GITLAB_API_PREFIX'), project_id)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, method='GET', params=params)

  @staticmethod
  def resolve_token(username, app):
    user = KeeperManager.resolve_user(username, app)
    return user.token

  @staticmethod
  def resolve_user(username, app):
    r = db.get_user_info(username)
    if r is None:
      app.logger.error("User: %s does not exists." % username)
      raise KeeperException(404, "User: %s does not exists." % username)
    return User(r['user_id'], username, r['token'])

  @staticmethod
  def resolve_branch_name(title, app):
    app.logger.debug("Resolve branch name with title: %s", title)
    return re.sub(r'\W', '-', title.lower()).strip('-')

  @staticmethod
  def resolve_project(username, project_name, app):
    token = KeeperManager.resolve_token(username, app)
    projects = KeeperManager.get_gitlab_projects(token, app)
    project = Project(project_name)
    found = False
    for p in projects:
      if p['path_with_namespace'] == project_name:
        project.project_id = p['id']
        found = True
        break
    if not found:
      raise KeeperException(404, "No project id found with provided project name: %s" % project_name)
    app.logger.debug("Obtained project: %s in project runner registration." % project)    
    return project

  @staticmethod
  def register_project_runner(username, project_name, runner_name, vm, snapshot, app):
    token = KeeperManager.resolve_token(username, app)
    project = KeeperManager.resolve_project(username, project_name, app)
    runners = KeeperManager.get_gitlab_runners(project.project_id, app)
    runner = Runner(runner_name)
    found = False
    for e in runners:
      if e['description'] == runner_name:
        runner.runner_id = e['id']
        found = True
        break
    if not found:
      raise KeeperException(404, "No runner id found with provided tag: %s" % runner_name)
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
  def add_user(username, token, app):
    r = KeeperManager.get_gitlab_user(username, token, app)
    if r is None:
      raise KeeperException(404, "No user id found with provided username: %s" % username)
    user = User(r['user_id'], r['username'])
    r = db.check_user(username, app)
    if r['cnt'] == 0:
      app.logger.debug("user: %s" % user)
      db.insert_user(user, app)
    else:
      app.logger.error("User: %s already exists." % (user.username,))
      raise KeeperException(409, "User: %s already exists." % (user.username,))

  @staticmethod
  def add_project(username, project_name, app):
    project = KeeperManager.resolve_project(username, project_name, app)
    app.logger.debug("Obtained project: %s in user creation with project." % project)
    user = KeeperManager.resolve_user(username, app)
    r = db.check_user_project(username, project.project_name, app)
    if r['cnt'] == 0:
      app.logger.debug("user: %s" % user)
      app.logger.debug("project: %s" % project)
      db.insert_project(project, app)
      db.insert_user_project(user, project, app)
    else:
      app.logger.error("User: %s with project: %s already exists." % (user.username, project.project_name))
      raise KeeperException(409, "User: %s with project: %s already exists." % (user.username, project.project_name))

  @staticmethod
  def post_issue_per_sonarqube(sonarqube_token, sonarqube_project_name, app):
    resp = KeeperManager.search_sonarqube_issues(sonarqube_token, sonarqube_project_name, app)
    issues = resp["issues"]
    if len(issues) == 0:
      raise KeeperException(404, "No found from SonarQube issues.")
    for issue in issues:
      username = issue["assignee"]
      user = KeeperManager.resolve_user(username, app)
      r = db.check_issue_exists(user["user_id"], issue["hash"])
      if r["cnt"] > 0:
        raise KeeperException(409, "User ID: %d with issue hash: %s already exists." % (user["user_id"], issue["hash"]))
        continue
      
      title = issue["message"]
      component = issue["component"]
      description = "Code file:" + component[component.index(":") + 1:]
      label = issue["severity"]

      app.logger.debug("Resolved issue title: {}".format(title))
      app.logger.debug("Resolved issue description: {}".format(description))
      app.logger.debug("Resolved issue label: {}".format(label))

      app.logger.debug("Resolved user as assignee: {}".format(user))
      assignee_project = username + "/" + sonarqube_project_name[sonarqube_project_name.index("-") + 1:]
      project = KeeperManager.resolve_project(username, assignee_project, app)
      app.logger.debug("Resolved project with path: {}".format(project))

      db.insert_issue_hash_with_user(user["user_id"], issue["hash"], app)
      KeeperManager.post_issue_to_assignee(project.project_id, title, description, label, username, app)
