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
  vm_name = request.args.get('vm_name', '')
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
  vm_name = request.args.get('vm_name', '')
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
  username = request.args.get('username', '')
  if username is None:
    return abort(400, "Username is required.")
  token = request.args.get('token', '')
  if token is None:
    return abort(400, "Token is required.")
  project_name = request.args.get('project_name', '')
  if project_name is None:
    return abort(400, "Project name is required.")
  try:
    KeeperManager.add_user_project(username, token, project_name, current_app)
  except KeeperException as e:
    return abort(500, e)
  return jsonify(message="Successful add user with project")


@bp.route('/register_runner', methods=['POST'])
def register_runner():
  username = request.args.get('username', '')
  if username is None:
    return abort(400, "Username is required.")
  project_name = request.args.get('project_name', '')
  if project_name is None:
    return abort(400, "Project name is required.")
  runner_tag = request.args.get('runner_tag', '')
  if runner_tag is None:
    return abort(400, "Runner tag is required.")

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
    KeeperManager.register_project_runner(username, project_name, runner_tag, vm, snapshot, current_app)
  except KeeperException as e:
    return abort(500, e)
  return jsonify(message="Successful register project runner.")


@bp.route('/unregister_runner', methods=['DELETE'])
def unregister_runner():
  runner_tag = request.args.get('runner_tag', '')
  if runner_tag is None:
    return abort(400, 'Runner tag is required.')
  try:
    KeeperManager.unregister_runner_by_tag(runner_tag, current_app)
  except KeeperException as e:
    return abort(500, e)
  return jsonify(message="Successful unregister project runner.")
  
  