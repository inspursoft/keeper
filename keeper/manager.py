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
    return SSHUtil.exec_script(self.current, "cd %s && vagrant" % vm_path, *operation)

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
  
  def force_delete_vm(self):
    vm_info = self.get_vm_info()
    return self.__base_vagrant_operation("destroy", "-f", vm_info.id)

  @staticmethod
  def get_gitlab_api_url():
    return parse.urljoin(get_info('GITLAB_URL'), get_info('GITLAB_API_PREFIX'))

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
  def request_gitlab_api(principle, request_url, app, method='POST', by_principle='project_id', params={}):
    r = None
    if by_principle == 'username':
      r = db.get_user_info(principle)
    elif by_principle == 'project_id':
      r = db.get_user_token_by_project(principle)
    if r is None:
      app.logger.error("Failed to get token with principle: %r", principle)
      raise KeeperException(404, "Failed to get token with principle: %r" % (principle,))
    app.logger.debug("Got token: %s", r['token'])
    resp = None
    default_headers={"PRIVATE-TOKEN": r['token']}
    if method == 'POST':
      resp = requests.post(request_url, headers=default_headers, params=params)
    elif method == 'GET':
      resp = requests.get(request_url, headers=default_headers, params=params)
    elif method == 'PUT':
      resp = requests.put(request_url, headers=default_headers, params=params)
    elif method == 'DELETE':
      resp = requests.delete(request_url, headers=default_headers, params=params)
    if resp.status_code >= 400:
      app.logger.error("Failed to request URL: %s with status code: %d with content: %s", request_url, resp.status_code, resp.content)
      raise KeeperException(resp.status_code, "Failed to request URL: %s with status code: %d with content: %s" % (request_url, resp.status_code, resp.content))
    try:
      return resp.json()
    except JSONDecodeError as e:
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
    app.logger.debug("Create branch: %s from %s with project_id: %d", branch_name, ref, project_id)
    request_url = "%s/projects/%d/repository/branches?branch=%s&ref=%s" % (KeeperManager.get_gitlab_api_url(), project_id, branch_name, ref)
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
    raise KeeperException(404, "No project id found with provided project name: %s" % project_name)

  @staticmethod
  def register_project_runner(username, project_name, runner_name, vm, snapshot=None, app=None):
    token = KeeperManager.resolve_token(username, app)
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
  def add_project(username, project_name, app):
    r = db.check_user_project(username, project_name, app)
    if r['cnt'] > 0:
      app.logger.error("User: %s with project: %s already exists." % (username, project_name))
      raise KeeperException(409, "User: %s with project: %s already exists." % (username, project_name))
    project = KeeperManager.resolve_user_project(username, project_name, app)
    user = KeeperManager.resolve_user(username, app)   
    app.logger.debug("Obtained user: %s" % user)
    db.insert_project(project, app)
    db.insert_user_project(user, project, app)
    
  @staticmethod
  def resolve_runner_token(username, project_name, app):
    project = KeeperManager.resolve_user_project(username, project_name, app)
    r = db.get_runner_token(username, project_name)
    if not r:
      raise KeeperException(404, 'No project runner token found with project: %s and username: %s' % (project_name, username))
    return r['runner_token']

  @staticmethod
  def update_runner_token(username, project_id, project_name, runner_token, app):
    project = KeeperManager.resolve_user_project(username, project_name, app, project_id=project_id)
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
    content = p.sub("%s/\g<tag>" % get_info("NGINX_PROXY"), content)
    return TemplateUtil.render_simple(content, **kwargs)

  @staticmethod
  def get_ip_provision(project_id, app):
    r = db.get_available_ip_by_project(project_id)
    if not r["id"]:
      raise KeeperException(404, "No IP provision found currently.")
    return IPProvision(r["id"], r["project_id"], r["ip_address"])

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
  def register_ip_runner(ip_provision_id, runner_id, pipeline_id, app):
    db.insert_ip_runner(ip_provision_id, runner_id, pipeline_id, app)

  @staticmethod
  def unregister_ip_runner(runner_id, app):
    db.remove_ip_runner(runner_id, app)

  @staticmethod
  def release_ip_runner_on_success(pipeline_id, app):
    r = db.get_ip_provision_by_pipeline(pipeline_id)
    if r and len(r) > 0:
      ip_provision_id = r["ip_provision_id"]
      ip_address = r["ip_address"]
      project_id = r["project_id"]
      db.update_ip_provision_by_id(ip_provision_id, 0, app)
      db.remove_ip_runner(ip_provision_id, app)
      app.logger.debug("Release IP: %s with project ID: %d as SUCCESS.", ip_address, project_id)

  @staticmethod
  def release_ip_runner_on_canceled(project_id, app):
    db.update_ip_provision_by_project_id(project_id, 0, app)
    db.remove_ip_runner_by_project_id(project_id, app)
    app.logger.debug("Release IP with project ID: %d as CANCELED.", project_id)
    
    