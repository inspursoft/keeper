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