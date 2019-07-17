from flask import (
  Blueprint, request, jsonify, current_app, url_for, abort
)

import subprocess
import os

from urllib.parse import urljoin

from keeper.manager import *

from threading import Thread

from keeper.model import User, Project, VM, Snapshot, Runner

from . import get_info

import paramiko

from flask.cli import with_appcontext

bp = Blueprint("handler", __name__, url_prefix="/api/v1")

@bp.route("/react")
def react():
  vm_name = request.args.get('vm_name', None)
  action = request.args.get('action', 'restore')
  if vm_name is None:
    return abort(400, "VM name is required.")
  try:
    manager = KeeperManager(current_app, vm_name)
    vm_runner = manager.get_vm_with_runner()
    dispatch_url = urljoin(vm_runner['keeper_url'], url_for('.snapshot', vm_name=vm_name))
    current = current_app._get_current_object()
    def subtask():
      with current.app_context():
        manager.dispatch_task(dispatch_url)
    if action == "restore":
      Thread(target=subtask).start()      
    else:
      current_app.logger.warning("Unsupport action %s to react." % action)
      return abort(412, "Unsupport action %s to react." % action)
  except KeeperException as e:
    current_app.logger.error(e)
    return abort(e.code, e.message)
  return jsonify(message="Action %s is being taken at remote: %s" % (action, vm_runner['keeper_url']))


@bp.route('/snapshot')
def snapshot():
  vm_name = request.args.get('vm_name', None)
  if vm_name is None:
    return abort(400, "VM name is required.")
  try:
    manager = KeeperManager(current_app, vm_name)
    vm_runner = manager.get_vm_with_runner()
    target = vm_runner['target']
    vm_name = vm_runner['vm_name']
    if manager.get_runner_id() is not None:
      manager.toggle_runner('false')
    snapshot_name = manager.get_vm_snapshot_name(vm_name)
    filepath = os.path.join(os.path.join(current_app.instance_path, '%s-restore-snapshot.sh' % target))
    current_app.logger.info(exec_script(current_app, filepath, vm_runner['vm_id'], snapshot_name))
  except KeeperException as e:
    current_app.logger.error(e)
    return abort(e.message, "Failed to execute script file: %s" % '%s-restore-snapshot.sh' % target)
  finally:
    if manager.get_runner_id() is not None:
      manager.toggle_runner('true')
  return jsonify(message="%s has been executed with restore action." % vm_name)
  

def exec_script(app, filepath, *args):
  try:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=get_info('HOST'), username=get_info('USERNAME'), password=get_info('PASSWORD'))
    app.logger.debug('{} {}'.format(filepath, ' '.join(args)))
    _, stdout, _ = client.exec_command('{} {}'.format(filepath, ' '.join(args)))
    result = stdout.read().decode()   
    return result
  except Exception as e:
    return 'Error occurred: {}'.format(e)
  finally:
    client.close()


@bp.route('/user', methods=['POST'])
def add_user():
  username = request.args.get('username', None)
  if username is None:
    return abort(400, "Username is required.")
  token = request.args.get('token', None)
  if token is None:
    return abort(400, "Token is required.")
  try:
    KeeperManager.add_user(username, token, current_app)
  except KeeperException as e:
    return abort(e.code, e.message)
  return jsonify(message="Successful added user.")


@bp.route('/user_project', methods=['POST'])
def add_project():
  username = request.args.get('username', None)
  if username is None:
    return abort(400, "Username is required.")
  project_name = request.args.get('project_name', None)
  if project_name is None:
    return abort(400, "Project name is required.")
  try:
    KeeperManager.add_project(username, project_name, current_app)
  except KeeperException as e:
    return abort(e.code, e.message)
  return jsonify(message="Successful added user with project")



@bp.route('/register_runner', methods=['POST'])
def register_runner():
  username = request.args.get('username', None)
  if username is None:
    return abort(400, "Username is required.")
  project_name = request.args.get('project_name', None)
  if project_name is None:
    return abort(400, "Project name is required.")
  runner_name = request.args.get('runner_name', None)
  if runner_name is None:
    return abort(400, "Runner name is required.")

  data = request.get_json()
  if data is None:
    return abort(400, "Bad input about project runner.")
  if "vm_id" not in data:
    return abort(400, "Missing vm_id in request body.")
  if "snapshot_name" not in data:
    return abort(400, "Missing snapshot_name in request body.")
  if "vm_name" not in data:
    data['vm_name'] = data['vm_id']
  if "target" not in data:
    data['target'] = 'vagrant'
  if "keeper_url" not in data:
    data["keeper_url"] = "http://localhost:5000"
  
  vm = VM(data['vm_id'], data['vm_name'], data['target'], data['keeper_url'])
  snapshot = Snapshot(data['vm_id'], data['snapshot_name'])
  try:
    KeeperManager.register_project_runner(username, project_name, runner_name, vm, snapshot, current_app)
  except KeeperException as e:
    return abort(e.code, e.message)
  return jsonify(message="Successful register project runner.")


@bp.route('/unregister_runner', methods=['DELETE'])
def unregister_runner():
  runner_name = request.args.get('runner_name', None)
  if runner_name is None:
    return abort(400, 'Runner name is required.')
  try:
    KeeperManager.unregister_runner_by_name(runner_name, current_app)
  except KeeperException as e:
    return abort(e.code, e.message)
  return jsonify(message="Successful unregister project runner.")


'''
{"object_kind":"merge_request","project":{"name":"myrepo0624"},"object_attributes":{"source_branch":"master","source_project_id":28,"state":"opened","last_commit":{"id":"40ed5e6e72feb12f8a0a87374b2822adb2271214"},"work_in_progress":false}}
'''
@bp.route('/hook', methods=["POST"])
def hook():
  username = request.args.get('username', None)
  if username is None:
    return abort(400, "Username is required.")
  data = request.get_json()
  if data is None:
    current_app.logger.error("None of request body.")
    return abort(400, "None of request body.")
  project_id = data["project"]["id"]
  object_attr = data["object_attributes"]
  source_project_id = object_attr['source_project_id']
  ref = object_attr["source_branch"]
  commit_id = object_attr["last_commit"]["id"]
  try:
    builds = KeeperManager.get_repo_commit_status(project_id, commit_id, current_app)
    for build in builds:
      if build['status'] == 'skipped':
        abort(422, "INFO: %s build skipped (reason: build %d is in \"%s\" status)" % (commit_id, build['id'], build['status']))
        return
    resp = KeeperManager.trigger_pipeline(source_project_id, ref, current_app)
    return jsonify(resp)
  except KeeperException as e:
    current_app.logger.error(e)
    return abort(e.code, e.message)

default_open_branch_prefix = 'fix:'
default_ref = 'dev'


@bp.route('/issue', methods=["POST"])
def issue():
  username = request.args.get('username', None)
  if username is None:
    return abort(400, "Username is required.")
  ref = request.args.get('ref', None)
  if ref is None:
    ref = default_ref
  open_branch_prefix = request.args.get('open_branch_prefix', None)
  if open_branch_prefix is None:
    open_branch_prefix = default_open_branch_prefix

  current_app.logger.info("Current ref branch is: %s", ref)
  current_app.logger.info("Current openning branch prefix is: %s", open_branch_prefix)
  data = request.get_json()
  if data is None:
    current_app.logger.error("None of request body.")
    return abort(400, "None of request body.")
  project = data['project']
  project_id = project['id']
  object_attr = data["object_attributes"]
  title = object_attr["title"]
  issue_iid = object_attr["iid"]

  s_title = title.lower()
  if not s_title.startswith(open_branch_prefix):
    current_app.logger.debug("No need to create branch with openning issue.")
    return jsonify(message="No need to create branch with openning issue.")

  try:
    branch_name = KeeperManager.resolve_branch_name(s_title[len(open_branch_prefix):])
    KeeperManager.create_branch(project_id, branch_name, ref, current_app)
    KeeperManager.comment_on_issue(project_id, issue_iid, "Branch: %s has been created." % (branch_name,), current_app)
    return jsonify(message="Successful created branch with issue.")
  except KeeperException as e:
    current_app.logger.error(e)
    return abort(e.code, e.message)


default_description = 'Assigned issue: %s to %s'
default_label = 'quality'
default_open_issue_prefix = "bug:"

@bp.route("/issues/assign", methods=["POST"])
def issue_assign():
  username = request.args.get('username', None)
  if username is None:
    return abort(400, "Username is required.")
  project_name = request.args.get('project_name', None)
  if project_name is None:
    return abort(400, "Project name is required.")
  data = request.get_json()
  if data is None:
    return abort(400, "Requested data is missing.")
  if "title" not in data:
    return abort(400, "Issue title is required.")
  if "assignee" not in data:
    return abort(400, "Issue assignee is required.")

  s_title = data['title'].lower()
  if not s_title.startswith(default_open_issue_prefix):
    current_app.logger.debug("No need to create issue to assignee as title is: %s", data['title'])
    return jsonify(message="No need to create issue to assignee as title is: %s" % data['title'])
  
  if "description" not in data:
    description = default_description % (data['title'], username)    
  if "label" not in data:
    label = default_label
  try:
    project = KeeperManager.resolve_project(username, project_name, current_app)
    KeeperManager.post_issue_to_assignee(project.project_id, data['title'], data['description'], data['label'], data['assignee'], current_app)
    return jsonify(message="Successful assigned issue to user: %s under project: %s" % (username, project_name))
  except KeeperException as e:
    current_app.logger.error(e)
    return abort(e.code, e.message)


@bp.route("/issues/per-sonarqube", methods=["POST"])
def issue_per_sonarqube():
  sonarqube_token = request.args.get("sonarqube_token", None)
  if sonarqube_token is None:
    return abort(400, "SonarQube token is required.")
  sonarqube_project_name = request.args.get("sonarqube_project_name", None)
  if sonarqube_token is None:
    return abort(400, "SonarQube project name is required.")
  try:
    KeeperManager.post_issue_per_sonarqube(sonarqube_token, sonarqube_project_name, current_app)
    return jsonify(message="Successful assigned issue to project: %s" % (sonarqube_project_name))
  except KeeperException as e:
    current_app.logger.error(e)
    return abort(e.code, e.message)


@bp.route("/issues/open-peer", methods=["POST"])
def issue_open_peer():
  ref = request.args.get('ref', None)
  if ref is None:
    ref = default_ref
  default_assignee = request.args.get('default_assignee', None)
  
  data = request.get_json()
  project = data["project"]
  project_id = project["id"]
  project_name = project["name"]
  object_attr = data["object_attributes"]
  issue_iid = object_attr["iid"]
  issue_title = object_attr["title"]
  branch_name = KeeperManager.resolve_branch_name("{}-{}".format(issue_iid, issue_title), current_app)
  current_app.logger.debug("Create branch: %s with ref: %s", branch_name, ref) 
  try:
    KeeperManager.get_branch(project_id, branch_name, current_app)
  except KeeperException as e:
    if e.code == 404:
      current_app.logger.debug("Creating branch: %s as it does not exists will create one.", branch_name)
      KeeperManager.create_branch(project_id, branch_name, ref, current_app)
    else:
      current_app.logger.error(e)
      return abort(e.code, e.message)
  try:
    assignee_id = object_attr["assignee_id"]
    milestone_id = object_attr["milestone_id"]
    if assignee_id is None or milestone_id is None:
      if assignee_id is None:
       assignee = KeeperManager.resolve_user(default_assignee, current_app)
       assignee_id = assignee["user_id"]
      if milestone_id is None:
        milestones = KeeperManager.get_all_milestones(project_id, {"state": "active"}, current_app) 
        if len(milestones) == 0:
          current_app.logger.error("No active milestones found with project ID: %d" % (project_id))
          return abort(404, "No active milestones found with project ID: %d" % (project_id))
        milestone_id = milestones[-1]["id"]
      KeeperManager.update_issue(project_id, issue_iid, {"assignee_ids": [assignee["user_id"]], "milestone_id": milestone_id}, current_app)
    KeeperManager.create_branch_per_assignee(project_name, assignee_id, branch_name, ref, current_app)
    return jsonify(message="Successful created branch: %s per assignee ID: %d" % (branch_name, assignee_id))
  except KeeperException as e:
    current_app.logger.error(e)
    return abort(e.code, e.message)