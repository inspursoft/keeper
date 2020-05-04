from flask import (
  Blueprint, request,  jsonify, current_app, abort, Response, url_for
)

from keeper.db import get_vm
from keeper.manager import KeeperManager, KeeperException
from keeper.util import SubTaskUtil
from keeper.model import VM, Snapshot

bp = Blueprint('vm', __name__, url_prefix="/api/v1")

def recycle_vm(current_app, vm_name, project_id, pipeline_id, status="N/A"):
  try:
    KeeperManager(current_app, vm_name).force_delete_vm()
  except KeeperException as e:
    current_app.logger.error(e.message)
    current_app.logger.error("VM: %s for project: %d does not exist, will clean up pipeline, runner info as failure...", vm_name, project_id)
    KeeperManager.release_ip_runner_on_failure(project_id, current_app)
  finally:
    KeeperManager.release_ip_runner_on_success(pipeline_id, status, current_app)
    KeeperManager.unregister_runner_by_name(vm_name, current_app)

@bp.route('/vm/simple', methods=["POST"])
def vm_simple():
  vm_name = request.args.get("name", None)
  if not vm_name:
    return abort(400, "VM name is required.")
  vm_conf = request.get_json()
  if "keeper_url" not in vm_conf:
    return abort(400, "Keeper URL is required.")
  if "target" not in vm_conf:
    return abort(400, "Target is required.")
  if "vm_id" not in vm_conf:
    return abort(400, "VM ID is required.")
  if "snapshot_name" not in vm_conf:
    return abort(400, "Snapshot name is required.")
  try:
    vm = VM(vm_conf["vm_id"], vm_name, vm_conf["target"], vm_conf["keeper_url"])
    sn = Snapshot(vm_conf["vm_id"], vm_conf["snapshot_name"])
    KeeperManager.add_vm_snapshot(vm, sn, current_app)
    message = "Successful submitted simple VM: %s" %(vm_name,)
    current_app.logger.debug(message)
    return message
  except KeeperException as e:
    message = "Failed to submitted simple VM: %s" %(e.message,)
    current_app.logger.error(message)
    return abort(e.code, message)

@bp.route('/vm', methods=["GET", "POST"])
def vm():
  vm_name = request.args.get('name', None)
  if vm_name is None:
    return abort(400, "VM name is required.")
  if request.method == "GET":
    info = get_vm(vm_name)
    if info is None:
      return abort(404, "No VM found with name: %s" % vm_name)
    return jsonify(dict(info))
  elif request.method == "POST":
    username = request.args.get('username', None)
    if not username:
      return abort(400, 'Username is required.')
    project_id = request.args.get('project_id', None)
    if not project_id:
      return abort(400, 'Project ID is required.')
    project_name = request.args.get('project_name', None)
    if not project_name:
      return abort(400, 'Project name is required.')
    status = request.args.get('status', None)
    if not status:
      return abort(400, 'Status is required.')
    ip_provision_id = request.args.get('ip_provision_id', None)
    if not ip_provision_id:
      return abort(400, "IP provision ID is required.")
    pipeline_id = request.args.get('pipeline_id', None)
    if not pipeline_id:
      return abort(400, "Pipeline ID is required.")
    vm_conf = request.get_json()
    if 'vm_box' not in vm_conf:
      return abort(400, 'VM box is required.')
    if 'vm_ip' not in vm_conf:
      return abort(400, 'VM IP is required.')
    if 'vm_memory' not in vm_conf:
      return abort(400, 'VM memory is required.')     
    if 'runner_tag' not in vm_conf:
      return abort(400, 'Runner tag is required.')
    try:
      current = current_app._get_current_object()
      def callback():
        KeeperManager.unregister_inrelevant_runner(project_id, vm_name, current)
        manager = KeeperManager(current, vm_name)
        if manager.check_vm_exists():
          recycle_vm(current, vm_name, project_id, pipeline_id)
        runner_token = KeeperManager.resolve_runner_token(username, project_name, current)
        manager.generate_vagrantfile(runner_token, vm_conf)
        manager.copy_vm_files()
        current.logger.debug(manager.create_vm())
        if KeeperManager.get_runner_cancel_status(project_id, current) and KeeperManager.powering_on == KeeperManager.get_runner_power_status(project_id, current):
          message = "VM: %s would be recycled as it has been signaled to cancel." % (vm_name,)
          current.logger.debug(message)
          recycle_vm(current, vm_name, project_id, pipeline_id)
          return jsonify(message=message)
        try:
          info = manager.get_vm_info()
          vm = VM(vm_id=info.id, vm_name=vm_name, target="AUTOMATED", keeper_url="N/A")
          runner = KeeperManager.register_project_runner(username, project_name, vm_name, vm, snapshot=None, app=current)
          KeeperManager.update_ip_runner(ip_provision_id, runner.runner_id, current)
        except KeeperException as e0:
          current.logger.error("Failed to get runner: %s", e0)
        finally:
          KeeperManager.update_runner_power_status(username, project_name, ip_provision_id, KeeperManager.powered_on, current)
      SubTaskUtil.set(current_app, callback).start()
      return jsonify(message="VM: %s has being created." % vm_name)
    except KeeperException as e:
      return abort(e.code, e.message)

@bp.route("/vm/info/<path:vm_name>", methods=["GET", "DELETE"])
def vm_info(vm_name):
  if vm_name is None:
    return abort(400, "VM name is required.")
  try:
    manager = KeeperManager(current_app, vm_name)
    info = manager.get_vm_info()
    if request.method == "GET":
      return jsonify(vm_id=info.id, vm_name=vm_name, vm_provider=info.provider,
      vm_status=info.status, vm_directory=info.directory)
    elif request.method == "DELETE":
      project_name = request.args.get("project_name", None)
      if not project_name:
        return abort(400, "Project name is required.")
      def callback():
        manager.force_delete_vm()
        manager.unregister_runner_by_name(vm_name, current_app)
      SubTaskUtil.set(current_app, callback).start()
      return jsonify(message="VM: %s is being deleted." % vm_name)
  except KeeperException as e:
    return abort(e.code, e.message)
