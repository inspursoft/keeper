from flask import (
  Blueprint, request,  jsonify, current_app, abort
)

from keeper.db import get_vm

bp = Blueprint('vm', __name__, url_prefix="/api/v1")

@bp.route('/vm')
def vm_info():
  vm_name = request.args.get('name', None)
  if vm_name is None:
    return abort(400, "VM name is required.")
  info = get_vm(vm_name)
  if info is None:
    return abort(404, "No VM found with name: %s" % vm_name)
  return jsonify(dict(info))