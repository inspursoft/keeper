from flask import (
  Blueprint, request,  jsonify, current_app, abort, Response
)

from keeper.db import get_vm
from keeper.manager import KeeperManager, KeeperException
from keeper.util import SubTaskUtil

bp = Blueprint('vm', __name__, url_prefix="/api/v1")

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
    data = request.get_json()
    manager = KeeperManager(current_app, vm_name)
    manager.generate_vagrantfile(vm_box=data["vm_box"], vm_ip=data["vm_ip"], vm_memory=data["vm_memory"])
    current = current_app._get_current_object()
    def callback():
      manager.copy_vm_files()
      current.logger.debug(manager.create_vm())
    SubTaskUtil.set(current_app, callback).start()
    return "VM: %s has being created." % vm_name

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
      SubTaskUtil.set(current_app, manager.force_delete_vm).start()
      return jsonify(message="VM: %s is being deleted." % vm_name)
  except KeeperException as e:
    return abort(e.code, e.message)
