from flask import (
  Blueprint, request, jsonify, current_app, url_for, abort
)

import subprocess
import os

from urllib.parse import urljoin

from keeper.manager import *

from threading import Thread

from keeper.model import User, Project, VM, Snapshot, Runner

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
    return abort(500, e)
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
    current_app.logger.info(exec_script(filepath, vm_runner['vm_id'], snapshot_name))
  except KeeperException as e:
    current_app.logger.error(e)
    return abort(500, "Failed to execute script file: %s" % '%s-restore-snapshot.sh' % target)
  finally:
    if manager.get_runner_id() is not None:
      manager.toggle_runner('true')
  return jsonify(message="%s has been executed with restore action." % vm_name)


def exec_script(filepath, *args):
  proc = subprocess.Popen([filepath] + list(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
  out, err = proc.communicate()
  if err is not None:
    raise Exception(err)
  return out


@bp.route('/user_project', methods=['POST'])
def add_user_project():
  username = request.args.get('username', None)
  if username is None:
    return abort(400, "Username is required.")
  token = request.args.get('token', None)
  if token is None:
    return abort(400, "Token is required.")
  project_name = request.args.get('project_name', None)
  if project_name is None:
    return abort(400, "Project name is required.")
  try:
    KeeperManager.add_user_project(username, token, project_name, current_app)
  except KeeperException as e:
    return abort(500, e)
  return jsonify(message="Successful add user with project")


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
    return abort(500, e)
  return jsonify(message="Successful register project runner.")


@bp.route('/unregister_runner', methods=['DELETE'])
def unregister_runner():
  runner_name = request.args.get('runner_name', None)
  if runner_name is None:
    return abort(400, 'Runner name is required.')
  try:
    KeeperManager.unregister_runner_by_name(runner_name, current_app)
  except KeeperException as e:
    return abort(500, e)
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
  project_name = data["project"]["name"]
  object_attr = data["object_attributes"]
  source_project_id = object_attr['source_project_id']
  ref = object_attr["source_branch"]
  commit_id = object_attr["last_commit"]["id"]
  try:
    token = KeeperManager.resolve_token(username, current_app)
    project = KeeperManager.resolve_project(username, username + '/' + project_name, token, current_app)
    builds = KeeperManager.get_repo_commit_status(project.project_id, commit_id, token, current_app)
    for build in builds:
      if build['status'] == 'skipped':
        abort(422, "INFO: %s build skipped (reason: build %d is in \"%s\" status)" % (commit_id, build['id'], build['status']))
        return
    resp = KeeperManager.trigger_pipeline(source_project_id, ref, current_app)
    return jsonify(resp)
  except KeeperException as e:
    current_app.logger.error(e)
    return abort(500, e)

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
  # current_app.logger.debug(data)
  project = data['project']
  project_id = project['id']
  object_attr = data["object_attributes"]
  title = object_attr["title"]
  issue_iid = object_attr["iid"]
  try:
    s_title = title.lower()
    if s_title.startswith(open_branch_prefix):
      branch_name = s_title[len(open_branch_prefix):].strip(' ').replace(' ', '-')
      KeeperManager.create_branch(project_id, branch_name, ref, current_app)
      KeeperManager.comment_on_issue(project_id, issue_iid, "Branch: %s has been created." % (branch_name,), current_app)
      return jsonify(message="Successful created branch with issue.")
    current_app.logger.debug("No need to create branch with openning issue.")
    return jsonify(message="No need to create branch with openning issue.")
  except KeeperException as e:
    current_app.logger.error(e)
    return abort(500, e)

  
  
