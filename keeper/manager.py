import requests
from requests.auth import HTTPBasicAuth

from keeper.model import *
from keeper import db
from keeper import get_info
from keeper.util import TemplateUtil, SSHUtil

import re
from urllib import parse
import os
from json.decoder import JSONDecodeError
from datetime import datetime, timedelta
import random

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
    request_url = "%s/runners/%d?private_token=%s" % (KeeperManager.get_gitlab_api_url(), self.get_runner_id(), self.get_token())
    resp = requests.put(request_url, data={'active': status})
    self.current.logger.debug("Requested URL: %s to toggle runner status as %s", request_url, status)
    if resp.status_code >= 400:
      raise KeeperException(resp.status_code, 'Failed to request with URL: %s' % request_url)

  def dispatch_task(self, dispatch_url):
    resp = requests.get(dispatch_url)
    self.current.logger.debug("Requested URL: %s with status: %d", dispatch_url, resp.status_code)
    if resp.status_code >= 400:
      raise KeeperException(resp.status_code, 'Failed to request with URL: %s' % dispatch_url)
  
  def generate_vagrantfile(self, runner_token, vm_conf):
    if not vm_conf:
      raise KeeperException(400, 'Missing VM configurations.')
    vm_conf["gitlab_url"] = get_info("GITLAB_URL")
    vm_conf["runner_name"] = self.vm_name
    vm_conf["runner_token"] = runner_token
    vagrant_file_path = os.path.join(get_info("LOCAL_OUTPUT"), self.vm_name)
    TemplateUtil.render_file(vagrant_file_path, "Vagrantfile", vm_conf)

  def copy_vm_files(self):
    local_vagrantfile_path = os.path.join(get_info("LOCAL_OUTPUT"), self.vm_name, "Vagrantfile")
    remote_dest_path = os.path.join(get_info("VM_DEST_PATH"), self.vm_name)
    # SSHUtil.secure_copy(self.current, get_info("VM_SRC_PATH"), remote_dest_path)
    SSHUtil.exec_script(self.current, "cp -R %s %s" % (get_info("VM_SRC_PATH"), remote_dest_path))
    SSHUtil.secure_copyfile(self.current, local_vagrantfile_path, remote_dest_path)
    
  
  def __base_vagrant_operation(self, *operation):
    vm_path = os.path.join(get_info("VM_DEST_PATH"), self.vm_name)
    return SSHUtil.exec_script(self.current, "cd %s && PATH=/usr/local/bin:$PATH vagrant" % vm_path, *operation)

  def create_vm(self):
    return self.__base_vagrant_operation("up")

  def get_global_status(self):
    return self.__base_vagrant_operation("global-status")

  def get_vm_info(self):
    raw_output = self.get_global_status()
    vm_global_status = VMGlobalStatus.parse(raw_output, self.vm_name)
    if vm_global_status is None:
      raise KeeperException(404, "VM: %s does not exist." % self.vm_name)
    return vm_global_status
  
  def check_vm_exists(self):
    try:
      self.get_vm_info()
      self.current.logger.debug("VM: %s already exists.", self.vm_name)
      return True
    except KeeperException:
      self.current.logger.debug("VM: %s does not exist.", self.vm_name)
      return False

  def force_delete_vm(self):
    vm_info = self.get_vm_info()
    return self.__base_vagrant_operation("destroy", "-f", vm_info.id)

  def get_custom_conf(self):
    conf = None
    if "CUSTOM_CONF" in self.current.config["SETUP"]:
      conf = get_info('CUSTOM_CONF')
    return conf
    
  @staticmethod
  def get_gitlab_api_url():
    return parse.urljoin(get_info('GITLAB_URL'), get_info('GITLAB_API_PREFIX'))

  @staticmethod
  def add_vm_snapshot(vm, snapshot, app):
    r = db.check_vm_snapshot(vm.vm_name, snapshot.snapshot_name, app)
    if not r:
      db.insert_vm(vm, app)
      db.insert_snapshot(snapshot, app)
    else:
      app.logger.error("VM: %s with snapshot: %s already exists." % (vm.vm_name, snapshot.snapshot_name))
      raise KeeperException(409, "VM: %s with snapshot: %s already exists." % (vm.vm_name, snapshot.snapshot_name))

  @staticmethod
  def get_gitlab_users(username, token, app):
    request_url = "%s/users?username=%s&private_token=%s" % (KeeperManager.get_gitlab_api_url(), username, token)
    resp = requests.get(request_url)
    if resp.status_code >= 400:
      app.logger.error("Failed to request URL: %s with status code: %d", request_url, resp.status_code)
      raise KeeperException(resp.status_code, "Failed to request URL: %s with status code: %d" % (request_url, resp.status_code))
    return resp.json()

  @staticmethod
  def get_gitlab_projects(token, app):
    request_url = "%s/projects?private_token=%s&per_page=200" % (KeeperManager.get_gitlab_api_url(), token)
    resp = requests.get(request_url)
    if resp.status_code >= 400:
      app.logger.error("Failed to request URL: %s with status code: %d", request_url, resp.status_code)
      raise KeeperException(resp.status_code, "Failed to request URL: %s with status code: %d" % (request_url, resp.status_code))
    return resp.json()

  @staticmethod
  def get_gitlab_runners(project_id, app):
    app.logger.debug("Get gitlab runner with project ID: %d", project_id)
    request_url = "%s/projects/%d/runners" % (KeeperManager.get_gitlab_api_url(), project_id)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, method='GET')

  @staticmethod
  def resolve_runner(project_id, runner_name, app):
    runners = KeeperManager.get_gitlab_runners(project_id, app)
    runner = Runner(runner_name)
    for r in runners:
      if r['description'] == runner_name:
        runner.runner_id = r['id']
        return runner
    rs = db.get_project_runner_by_name(runner_name)
    for r in rs:
      runner.runner_id = r['runner_id']
      runner.runner_name = runner_name
      return runner
    raise KeeperException(404, "No runner id found with provided tag: %s" % runner_name)

  @staticmethod
  def update_runner(project_id, runner_id, updates, app):
    app.logger.debug("Update runner with project ID: %d, runner ID: %d and updates: %s", project_id, runner_id, updates)
    request_url = "%s/runners/%d" % (KeeperManager.get_gitlab_api_url(), runner_id)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, method='PUT', params=updates)

  @staticmethod
  def remove_runner(project_id, runner_id, app):
    app.logger.debug("Remove runner with project ID: %d and runner ID: %d", project_id, runner_id)
    request_url = "%s/runners/%d" % (KeeperManager.get_gitlab_api_url(), runner_id)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, method='DELETE')

  @staticmethod
  def get_repo_commit_status(project_id, commit_id, app):
    app.logger.debug("Get repo with project ID: %d and commit ID: %d", project_id, commit_id)
    request_url = "%s/projects/%d/repository/commits/%s/statuses" % (KeeperManager.get_gitlab_api_url(), project_id, commit_id)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, method='GET')

  @staticmethod
  def request_gitlab_api(principle, request_url, app, method='POST', by_principle='project_id', params={}, resp_raw=False, dismiss_exception=False):
    r = None
    if by_principle == 'username':
      r = db.get_user_info(principle)
    elif by_principle == 'project_id':
      r = db.get_user_token_by_project(principle)
    if r is None:
      app.logger.error("Failed to get token with principle: %r", principle)
      raise KeeperException(404, "Failed to get token with principle: %r" % (principle,))
    app.logger.debug("Got token: %s, params: %s", r['token'], params)
    resp = None
    default_headers={"PRIVATE-TOKEN": r['token']}
    if method == 'POST':
      resp = requests.post(request_url, headers=default_headers, json=params)
    elif method == 'GET':
      resp = requests.get(request_url, headers=default_headers)
    elif method == 'PUT':
      resp = requests.put(request_url, headers=default_headers, json=params)
    elif method == 'DELETE':
      resp = requests.delete(request_url, headers=default_headers)
    if not dismiss_exception or resp.status_code >= 400:
      app.logger.error("Failed to request URL: %s with status code: %d with content: %s", request_url, resp.status_code, resp.content)
      raise KeeperException(resp.status_code, "Failed to request URL: %s with status code: %d with content: %s" % (request_url, resp.status_code, resp.content))
    try:
      if resp_raw:
        return resp.text
      return resp.json()
    except JSONDecodeError:
      pass

  @staticmethod
  def request_sonarqube_api(sonarqube_token, request_url, app):
    app.logger.debug("Got Sonarqube token: %s", sonarqube_token)
    resp = requests.get(request_url, auth=HTTPBasicAuth(sonarqube_token,""))
    if resp.status_code >= 400:
      app.logger.error("Failed to request URL: %s with status code: %d with content: %s", request_url, resp.status_code, resp.content)
      raise KeeperException(resp.status_code, "Failed to request URL: %s with status code: %d with content: %s" % (request_url, resp.status_code, resp.content))
    return resp.json()

  @staticmethod
  def search_sonarqube_issues(sonarqube_token, sonarqube_project_name, app, severities="CRITICAL", created_in_last="10d"):
    app.logger.debug("Request Sonarqube issues for project: %s", sonarqube_project_name)
    request_url = "%s/issues/search?componentKeys=%s&severities=%s&createdInLast=%s" % (get_info('SONARQUBE_API_PREFIX'), sonarqube_project_name, severities, created_in_last)
    app.logger.debug("Request Sonarqube API: %s", request_url)
    return KeeperManager.request_sonarqube_api(sonarqube_token, request_url, app)

  @staticmethod
  def trigger_pipeline(project_id, ref, app):
    app.logger.debug("Trigger pipeline with project ID: %d", project_id)
    request_url = "%s/projects/%d/pipeline?ref=%s" % (KeeperManager.get_gitlab_api_url(), project_id, ref)
    return KeeperManager.request_gitlab_api(project_id, request_url, app)

  @staticmethod
  def retry_pipeline(project_id, pipeline_id, app):
    app.logger.debug("Retry pipeline with project ID: %d, pipeline ID: %d", project_id, pipeline_id)
    request_url = "%s/projects/%d/pipelines/%d/retry" % (KeeperManager.get_gitlab_api_url(), project_id, pipeline_id)
    return KeeperManager.request_gitlab_api(project_id, request_url, app)

  @staticmethod
  def cancel_pipeline(project_id, pipeline_id, app):
    app.logger.debug("Cancel pipeline with project ID: %d, pipeline ID: %d", project_id, pipeline_id)
    request_url = "%s/projects/%d/pipelines/%d/cancel" % (KeeperManager.get_gitlab_api_url(), project_id, pipeline_id)
    return KeeperManager.request_gitlab_api(project_id, request_url, app)

  @staticmethod
  def create_branch(project_id, branch_name, ref, app):
    app.logger.debug("Create branch: %s from %s with project ID: %d", branch_name, ref, project_id)
    request_url = "%s/projects/%d/repository/branches?branch=%s&ref=%s" % (KeeperManager.get_gitlab_api_url(), project_id, branch_name, ref)
    return KeeperManager.request_gitlab_api(project_id, request_url, app)

  @staticmethod
  def commit_files(project_id, branch_name, commit_message, actions, app):
    app.logger.debug("Commit files to the branch: %s with project ID: %d", branch_name, project_id)
    request_url = "%s/projects/%d/repository/commits" % (KeeperManager.get_gitlab_api_url(), project_id)
    params = {"branch": branch_name, "start_branch": branch_name, "commit_message": commit_message, "actions": actions}
    return KeeperManager.request_gitlab_api(project_id, request_url, app, params=params)

  @staticmethod
  def resolve_action_from_store(category, file_type, app):
    store = KeeperManager.get_from_store(category, app)
    contents = ""
    if file_type == ".sh":
      contents = "#!/bin/bash\n"
    for key in store:
      if file_type == ".md":
        contents += "*" + " " + key + ":" + store[key]
      elif file_type == ".sh":
        contents += key + "=" + '"{}"'.format(store[key])
      contents += "\n"
    app.logger.debug("Generated contents with file type: %s, content: %s", file_type, contents)
    return contents

  @staticmethod
  def create_merge_request(project_id, source_branch, target_branch, title, description, app):
    app.logger.debug("Create merge request from branch: %s to %s, with title: %s, description: %s and project ID: %d", source_branch, target_branch, title, description, project_id)
    request_url = "%s/projects/%d/merge_requests?source_branch=%s&target_branch=%s&title=%s&description=%s" % (KeeperManager.get_gitlab_api_url(), project_id, source_branch, target_branch, title, description)
    return KeeperManager.request_gitlab_api(project_id, request_url, app)

  @staticmethod
  def create_branch_per_assignee(project_name, assignee_id, branch_name, ref, app):
    r = db.get_user_by_id(assignee_id)
    if not r:
      app.logger.error("Failed to get user by assignee ID: %d", assignee_id)
      raise KeeperException(404, "Failed to get user by assignee ID: %d" % (assignee_id,))
    repo_name = "%s/%s" % (r["username"], project_name)
    r = db.get_project_by_user_id(repo_name, assignee_id)
    if r is None:
      app.logger.error("Failed to get project by assignee ID: %d", assignee_id)
      raise KeeperException(404, "Failed to get project by assignee ID: %s" % (assignee_id,))
    assignee = r['username']
    target_project_id = r['project_id']
    app.logger.debug("Create branch: %s per assignee: %s to project: %s", branch_name, assignee, project_name)
    try:
      KeeperManager.get_branch(target_project_id, branch_name, app)
    except KeeperException as e:
      app.logger.error("Branch: %s already exist to project: %s for assignee: %s, with error: %s", branch_name, project_name, assignee, e)
    return KeeperManager.create_branch(target_project_id, branch_name, ref, app)

  @staticmethod
  def resolve_due_date(created_at, labels, app):
    if len(labels) == 0:
      message = "No need to set due date as it has no label."
      app.logger.debug("No need to set due date as it has no label.")
      raise KeeperException(404, message)

    due_date = ""
    for c in labels:
      title = c["title"].lower()
      if title not in ["critical"]:
        app.logger.debug("No need to set due date as not matched.")
        continue
      c_time = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S %Z")
      if title == "critical":
        c_time += timedelta(days=0)
        app.logger.debug("Set due date per label is: %s", title)
        due_date = datetime.strftime(c_time, "%Y-%m-%d")
    if due_date == "":
      message = "No need to set due date as no matched label."
      app.logger.debug(message)
      raise KeeperException(404, message)
    return due_date

  @staticmethod
  def get_branch(project_id, branch_name, app):
    app.logger.debug("Get branch with project ID: %d", project_id)
    request_url = "%s/projects/%d/repository/branches/%s" % (KeeperManager.get_gitlab_api_url(), project_id, branch_name)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, method='GET')

  @staticmethod
  def comment_on_issue(username, project_id, issue_iid, message, app):
    app.logger.debug("Comment on issue to project ID: %d on issue IID: %d, with message: %s", project_id, issue_iid, message)
    request_url = "%s/projects/%d/issues/%d/notes?body=%s" % (KeeperManager.get_gitlab_api_url(), project_id, issue_iid, message)
    return KeeperManager.request_gitlab_api(username, request_url, app, by_principle="username")

  @staticmethod
  def comment_on_merge_request(username, project_id, mr_iid, message, app):
    app.logger.debug("Comment on MR to project ID: %d on IID: %d, with message: %s", project_id, mr_iid, message)
    request_url = "%s/projects/%d/merge_requests/%d/notes?body=%s" % (KeeperManager.get_gitlab_api_url(), project_id, mr_iid, message)
    return KeeperManager.request_gitlab_api(username, request_url, app, by_principle="username")

  @staticmethod
  def comment_on_commit(username, project_id, commit_sha, message, app):
    app.logger.debug("Comment on commit to project ID: %d on commit SHA: %s, with message: %s", project_id, commit_sha, message)
    request_url = "%s/projects/%d/repository/commits/%s/comments" % (KeeperManager.get_gitlab_api_url(), project_id, commit_sha)
    return KeeperManager.request_gitlab_api(username, request_url, app, by_principle="username", params = {"note": message})

  @staticmethod
  def post_issue_to_assignee(project_id, title, description, label, assignee, app):
    app.logger.debug("Post issue to project ID: %d with title: %s, label: %s, description: %s ", project_id, title, description, label)
    user = KeeperManager.resolve_user(assignee, app)
    request_url = "%s/projects/%d/issues?title=%s&description=%s&labels=%s&assignee_ids=%d" % (KeeperManager.get_gitlab_api_url(), project_id, title, description, label, user.user_id)
    return KeeperManager.request_gitlab_api(project_id, request_url, app)

  @staticmethod
  def update_issue(project_id, issue_iid, updates, app):
    app.logger.debug("Update issue to project ID: %d to issue IID: %d with changes: %s", project_id, issue_iid, updates)
    request_url = "%s/projects/%d/issues/%d" % (KeeperManager.get_gitlab_api_url(), project_id, issue_iid)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, method="PUT", params=updates)

  @staticmethod
  def get_milestone(project_id, milestone_id, app):
    app.logger.debug("Get milestone with project ID: %d with milestone ID: %d")
    request_url = "%s/projects/%d/milestones/%d" % (KeeperManager.get_gitlab_api_url(), project_id, milestone_id)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, method='GET')

  @staticmethod
  def get_all_milestones(project_id, params, app):
    app.logger.debug("Get all milestones with project ID: %d", project_id)
    request_url = "%s/projects/%d/milestones" % (KeeperManager.get_gitlab_api_url(), project_id)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, method='GET', params=params)

  @staticmethod
  def create_discussion_to_merge_request(project_id, merge_request_id, comments, app):
    app.logger.debug("Create discussion to merge request with project ID: %d, merge request ID: %d", project_id, merge_request_id)
    request_url = "%s/projects/%d/merge_requests/%d/discussions" % (KeeperManager.get_gitlab_api_url(), project_id, merge_request_id)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, params={"body": comments})

  @staticmethod
  def create_related_issue_to_merge_request(project_id, merge_request_id, title, app):
    app.logger.debug("Create related issue to merge request ID: %d", merge_request_id)
    request_url = "%s/projects/%d/issues" % (KeeperManager.get_gitlab_api_url(), project_id)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, params={"merge_request_to_resolve_discussions_of": merge_request_id, "discussion_to_resolve": "LGTM", "title": title})

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
    project = Project(project_name)
    token = KeeperManager.resolve_token(username, app)
    projects = KeeperManager.get_gitlab_projects(token, app)
    for p in projects:
      if p['path_with_namespace'] == project_name:
        project.project_id = p['id']
        app.logger.debug("Obtained project: %s in project runner registration." % project) 
        return project
    app.logger.debug("Retrieve project ID from DB store.")
    u = db.get_user_info(username)
    if not u:
      raise KeeperException(404, "No username found with provided name: %s" % username)
    p = db.get_project_by_user_id(project_name, u["user_id"])
    if not p:
      raise KeeperException(404, "No project found with provided name: %s, user ID: %d"% (project_name, u["user_id"]))
    project.project_id = p["project_id"]
    return project

  @staticmethod
  def register_project_runner(username, project_name, runner_name, vm, snapshot=None, app=None):
    project = KeeperManager.resolve_project(username, project_name, app)
    runner = KeeperManager.resolve_runner(project.project_id, runner_name, app)
    app.logger.debug("Obtained runner: %s in project runner registration." % runner)    
    if not snapshot:
      snapshot = Snapshot(vm.vm_id, 'N/A')
    r = db.check_project_runner(project_name, vm.vm_name, runner.runner_id, snapshot.snapshot_name, app)
    if r['cnt'] == 0:
      db.insert_runner(runner, app)
      db.insert_project_runner(project, vm, runner, app)
      db.insert_vm(vm, app)
      db.insert_snapshot(snapshot, app)
      return runner
    else:
      app.logger.error("Project: %s with runner: %d, VM: %s and snapshot: %s already exists."
         % (project.project_name, runner.runner_id, vm.vm_name, snapshot.snapshot_name))
      raise KeeperException(409, "Project: %s with runner: %d, VM: %s and snapshot: %s already exists."
         % (project.project_name, runner.runner_id, vm.vm_name, snapshot.snapshot_name))

  @staticmethod
  def unregister_runner_by_name(runner_name, app):
    rs = db.get_project_runner_by_name(runner_name)
    if len(rs) == 0:
      app.logger.error("Runner name: %s does not exist." % runner_name)
    for r in rs:
      try:
        KeeperManager.remove_runner(r['project_id'], r['runner_id'], app)
      except KeeperException as e:
        app.logger.error("Error occurred while removing runner via API: %s", e)
      db.delete_project_runner(r['project_id'], r['runner_id'], app)
      db.delete_runner(r['runner_id'], app)
      db.delete_vm(r['vm_id'], app)
      db.delete_snapshot(r['snapshot_name'], app)
      SSHUtil.exec_script(app, "rm", '-rf', os.path.join(get_info("VM_DEST_PATH"), runner_name))
      
  @staticmethod
  def unregister_inrelevant_runner(project_id, runner_name, app):
    runners = KeeperManager.get_gitlab_runners(int(project_id), app)
    for r in runners:
      current_runner_name = r['description'] 
      if current_runner_name != runner_name:
        try:
          KeeperManager.remove_runner(int(project_id), int(r['id']), app)
        except KeeperException as e:
          app.logger.error("Error occurred while removing runner via API: %s", e)
        KeeperManager.unregister_runner_by_name(current_runner_name, app)
        
  @staticmethod
  def add_user(username, token, app):
    r = db.check_user(username, app)
    if r['cnt'] > 0:
      app.logger.error("User: %s already exists." % (username,))
      raise KeeperException(409, "User: %s already exists." % (username,))
    users = KeeperManager.get_gitlab_users(username, token, app)
    if len(users) == 0:
      raise KeeperException(404, "No user id found with provided username: %s" % username)
    user = users[0]
    db.insert_user(User(user['id'], username, token), app)

  @staticmethod
  def resolve_user_project(username, project_name, app):
    project = KeeperManager.resolve_project(username, project_name, app)
    app.logger.debug("Obtained project: %s in user creation with project." % project)
    return project

  @staticmethod
  def add_project(username, project_name, app, project_id=None):
    r = db.check_user_project(username, project_name, app)
    if r['cnt'] > 0:
      app.logger.error("User: %s with project: %s already exists." % (username, project_name))
      raise KeeperException(409, "User: %s with project: %s already exists." % (username, project_name))
    project = Project(project_name)
    if not project_id:
      project = KeeperManager.resolve_user_project(username, project_name, app)
    else:
      app.logger.debug("Use specified project ID: %s to the project: %s", project_id, project_name)
      project.project_id = project_id
    user = KeeperManager.resolve_user(username, app)   
    app.logger.debug("Obtained user: %s" % user)
    db.insert_project(project, app)
    db.insert_user_project(user, project, app)
    
  @staticmethod
  def resolve_runner_token(username, project_name, app):
    r = db.get_runner_token(username, project_name)
    if not r:
      raise KeeperException(404, 'No project runner token found with project: %s and username: %s' % (project_name, username))
    return r['runner_token']

  @staticmethod
  def update_runner_token(username, project_name, runner_token, app):
    project = KeeperManager.resolve_user_project(username, project_name, app)
    db.update_runner_token(runner_token, project.project_id, app)

  @staticmethod
  def post_issue_per_sonarqube(sonarqube_token, sonarqube_project_name, serverties, created_in_last, app):
    resp = KeeperManager.search_sonarqube_issues(sonarqube_token, sonarqube_project_name, app, serverties, created_in_last)
    issues = resp["issues"]
    if len(issues) == 0:
      raise KeeperException(404, "No found from SonarQube issues.")
    for issue in issues:
      username = issue["assignee"]
      user = KeeperManager.resolve_user(username, app)
      r = db.check_issue_exists(user.user_id, issue["hash"])
      if r["cnt"] > 0:
        raise KeeperException(409, "User ID: %d with issue hash: %s already exists." % (user.user_id, issue["hash"]))
      
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

      db.insert_issue_hash_with_user(user.user_id, issue["hash"], app)
      KeeperManager.post_issue_to_assignee(project.project_id, title, description, label, username, app)

  @staticmethod
  def get_note_template(name):
    r = db.get_note_template(name)
    if r is None:
      raise KeeperException(404, "Cannot find note template with name: %s" % (name,))
    return NoteTemplate(r["template_name"], r["template_content"])
  
  @staticmethod
  def render_note_with_template(content, **kwargs):
    p = re.compile(r"\[(?P<tag>[^\]]+)\]")
    content = p.sub(r"%s/\g<tag>" % get_info("NGINX_PROXY"), content)
    return TemplateUtil.render_simple(content, **kwargs)

  @staticmethod
  def get_ip_provision(project_id, app):
    r = db.get_reserved_runner_by_project(project_id)
    if not r:
      ips = db.get_available_ip()
      if len(ips) == 0:
        raise KeeperException(404, "No IP provision found currently.")
      ip = ips[random.randint(1, len(ips)) - 1]
      app.logger.debug("Allocated IP: %s, with ID: %s", ip["ip_address"], ip["id"])
      return IPProvision(ip["id"], ip["ip_address"])
    raise KeeperException(409, "IP runner already reserved.")

  @staticmethod
  def reserve_ip_provision(ip_provision_id, app):
    db.update_ip_provision_by_id(ip_provision_id, 1, app)

  @staticmethod
  def get_ip_provision_by_pipeline(pipeline_id, app):
    r = db.get_ip_provision_by_pipeline(pipeline_id)
    if r and r["ip_provision_id"] > 0:
      app.logger.debug("Pipeline: %d already allocated runner with IP: %s", r['pipeline_id'], r['ip_address'])
      return True
    return False
  
  @staticmethod
  def register_ip_runner(ip_provision_id, pipeline_id, project_id, app):
    db.insert_ip_runner(ip_provision_id, pipeline_id, project_id, app)

  @staticmethod
  def update_ip_runner(ip_provision_id, runner_id, app):
    db.update_ip_runner(ip_provision_id, runner_id, app)

  @staticmethod
  def unregister_ip_runner(runner_id, app):
    db.remove_ip_runner(runner_id, app)

  @staticmethod
  def release_ip_runner_on_success(pipeline_id, status, app):
    app.logger.debug("Releasing pipeline ID: %s with status: %s", pipeline_id, status)
    r = db.get_ip_provision_by_pipeline(pipeline_id)
    if r:
      ip_provision_id = r["ip_provision_id"]
      ip_address = r["ip_address"]
      db.update_ip_provision_by_id(ip_provision_id, 0, app)
      db.remove_ip_runner(ip_provision_id, app)
      app.logger.debug("Released IP: %s as %s.", ip_address, status)
      
  @staticmethod
  def register_runner(username, project_name, config, app):
    project = KeeperManager.resolve_project(username, project_name, app)
    project_id = project.project_id
    runner_token = config["runner_token"]
    def t_callback():
      db.update_runner_token(runner_token, project_id, app)
    db.DBT.execute(app, t_callback)
    app.logger.debug("Registered runner with project ID: %d and token: %s", project_id, runner_token)

  @staticmethod
  def unregister_runner(username, project_name, app):
    project = KeeperManager.resolve_project(username, project_name, app)
    project_id = project.project_id
    def t_callback():
      db.remove_ip_runner_by_project_id(project_id, app)
      db.update_runner_token(None, project_id, app)
    db.DBT.execute(app, t_callback)
    app.logger.debug("Unregistered runner with project ID: %d", project_id)

  @staticmethod
  def get_from_store(category, app):
    r = db.get_from_store(category, app)
    if not r or len(r) == 0:
      message = "None of result for store with category: %s" % (category,)
      app.logger.error(message)
      raise KeeperException(404, message)
    stored = {}
    for s in r:
      stored[s["item_key"]] = s["item_val"]
    return stored

  @staticmethod
  def add_to_store(category, store, app):
    for key in store:
      val = store[key]
      db.insert_into_store(category, key, val, app)
      app.logger.debug("Inserted or updated category: %s with key: %s, val: %s", category, key, val)
  
  @staticmethod
  def remove_from_store(category, app):
    db.delete_from_store(category, app)
    app.logger.debug("Removed category: %s", category)

  @staticmethod
  def resolve_project_with_priority(username, project_name, app):
    project = KeeperManager.resolve_project(username, project_name, app)
    r = db.get_project_with_priority(project.project_id)
    if not r:
      raise KeeperException(400, "Project info is required.")
    project.priority = r['priority']
    return project

  @staticmethod
  def trigger_legacy_pipeline(project_id, token, ref, params, app):
    r = db.get_reserved_runner_by_project(project_id)
    if r:
      raise KeeperException(409, "Project ID: %s for pipeline ID: %s was already reserved." %(r["project_id"], r["pipeline_id"]))
    app.logger.debug("Trigger pipeline with project ID: %s, token: %s and ref: %s", project_id, token, ref)
    request_url = "%s/projects/%d/trigger/pipeline" % (KeeperManager.get_gitlab_api_url(), project_id)
    default = {"token": token, "ref": ref}
    req_params = {}
    for key, value in params.items():
      req_params["variables[%s]" % (key,)] = value
    app.logger.debug("Trigger legacy pipeline with requested params: %s", req_params)
    merged = {**default, **req_params}
    resp = requests.post(request_url, data=merged)
    if resp.status_code >= 400:
      raise KeeperException(resp.status_code, resp.text)
    app.logger.debug("Requested with URL: %s, responed: %s with status code: %s", request_url, resp.text, resp.status_code)

  @staticmethod
  def get_config_variables(project_id, app):
    app.logger.debug("Get config variables with project ID: %s", project_id)
    request_url = "%s/projects/%d/variables" % (KeeperManager.get_gitlab_api_url(), project_id)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, method="GET")

  @staticmethod
  def add_config_variable(project_id, key, value, app):
    app.logger.debug("Add config variable - key: %s, value: %s with project ID: %s", key, value, project_id)
    request_url = "%s/projects/%d/variables" % (KeeperManager.get_gitlab_api_url(), project_id)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, params={"key": key, "value": value})

  @staticmethod
  def update_config_variable(project_id, key, value, app):
    app.logger.debug("Update config variable - key: %s, value: %s with project ID: %s", key, value, project_id)
    request_url = "%s/projects/%d/variables/%s" % (KeeperManager.get_gitlab_api_url(), project_id, key)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, params={"value": value}, method="PUT")

  @staticmethod
  def add_or_update_repository_file(project_id, action, file_path, content, branch, username, app):
    if not action or action == "":
      raise KeeperException(400, "Action for target is required.")
    elif action not in ["create", "update"]:
      raise KeeperException(400, "Only supporting create/update actions.")
    app.logger.debug("%s repository file: %s to the branch: %s with project ID: %s", action.capitalize(), file_path, branch, project_id)
    request_url = "%s/projects/%d/repository/files/%s" % (KeeperManager.get_gitlab_api_url(), project_id, file_path)
    method = "POST"
    if action == "update":
      method = "PUT"
    params = {"branch": branch, 
      "author_name": username, 
      "author_email": "%s@inspur.com" % (username,), 
      "content": content,   
      "commit_message": "%s for file: %s" % (action.capitalize(), file_path)}
    app.logger.debug("File: %s with content: %s", file_path, content)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, method=method, params=params, dismiss_exception=True)

  @staticmethod
  def get_repository_raw_file(project_id, file_path, branch, app):
    app.logger.debug("Get file %s from repository with project ID: %s", file_path, project_id)
    request_url = "%s/projects/%d/repository/files/%s/raw?ref=%s" % (KeeperManager.get_gitlab_api_url(), project_id, file_path, branch)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, method="GET", resp_raw=True)

  @staticmethod
  def delete_config_variable(project_id, key, app):
    app.logger.debug("Delete config variable - key: %s with project ID: %s", key, project_id)
    request_url = "%s/projects/%d/variables/%s" % (KeeperManager.get_gitlab_api_url(), project_id, key)
    return KeeperManager.request_gitlab_api(project_id, request_url, app, method="DELETE")

  @staticmethod
  def resolve_config_variables(config_project_id, target_project_id, file_path, branch, app):
    last_variables = KeeperManager.get_config_variables(target_project_id, app)
    content = KeeperManager.get_repository_raw_file(config_project_id, file_path, branch, app)
    app.logger.debug("File path: %s", file_path)
    app.logger.debug("Content: %s", content)
    current_variables = {}
    for line in content.splitlines():
      if not line.find("=") or line.startswith("#"):
        app.logger.debug("Bypass for none of equal sign or commented in line: %s", line)
        continue
      parts = line.split("=")
      if len(parts) < 2:
        continue
      current_variables[parts[0].strip()] = parts[1].strip()
    app.logger.debug("Current config variables: %s", current_variables)
    for current_key in list(current_variables.keys()):
      current_value = current_variables[current_key]
      for index, last_config in enumerate(last_variables):
        if last_config["key"] == current_key:
          KeeperManager.update_config_variable(target_project_id, current_key, current_value, app)
          del current_variables[current_key]
          last_variables.pop(index)
          break
    for config in last_variables:
      KeeperManager.delete_config_variable(target_project_id, config["key"], app)
    for key, value in current_variables.items():
      KeeperManager.add_config_variable(target_project_id, key, value, app)