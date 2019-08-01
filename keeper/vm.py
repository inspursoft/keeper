from flask import (
  Blueprint, request,  jsonify, current_app, abort, Response
)
from threading import Thread

from keeper.db import get_vm
from keeper.manager import KeeperManager

bp = Blueprint('vm', __name__, url_prefix="/api/v1")

@bp.route('/vm', methods=["GET", "POST"])
def vm_info():
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
    def subtask():
      with current.app_context():
        manager.copy_vm_files()
        current.logger.debug(manager.create_vm())
    Thread(target=subtask).start()
    return "VM: %s has being created." % vm_name