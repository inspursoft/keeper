from flask import (
  Blueprint, abort, request, current_app, jsonify
)

from keeper.manager import *
from werkzeug.utils import secure_filename
import tarfile

bp = Blueprint("assistant", __name__, url_prefix="/api/v1")

default_issuer = "reporter"

@bp.route("/notes/<path:project_name>", methods=["POST"])
def note_on_commit(project_name):
  if project_name is None:
    return abort(400, "Project name is required.")
  commit_sha = request.args.get("sha", None)
  if commit_sha is None:
    return abort(400, "Commit SHA is required.")
  template_name = request.args.get("name", None)
  if template_name is None:
    return abort(400, "The name of template is required.")
  issuer = request.args.get("issuer", default_issuer)
  entries = {}
  try:
    entries = request.get_json()
  except Exception as e:
    current_app.logger.error(e)
  try:
    template = KeeperManager.get_note_template(template_name)
    current_app.logger.debug("Template before rendered: %s", template.content)
    message = KeeperManager.render_note_with_template(template.content, **entries)
    current_app.logger.debug("Rendered template content: %s", template.content)
    project = KeeperManager.resolve_project(issuer, project_name, current_app)
    KeeperManager.comment_on_commit(issuer, project.project_id, commit_sha, message, current_app)
    return jsonify(message="Successful commented notes on commit: %s to the repo: %s" % (commit_sha, project.project_name))
  except KeeperException as e:
    current_app.logger.error(e)
    return abort(e.code, e.message)

@bp.route("/notes/template/<name>", methods=["GET", "POST"])
def manage_note_template(name):
  if request.method == "GET":
    if name is None:
      return abort(400, "Note template name is required.")
    try:
      template = KeeperManager.get_note_template(name)
      return jsonify(name=template.name, content=template.content)
    except KeeperException as e:
      current_app.logger.error(e)
      return abort(e.code, e.message)
  elif request.method == "POST":
    data = request.get_json()
    if data is None:
      return abort(400, "Request body is required.")
    if "content" not in data:
      return abort(400, "Content in request body is required.")
    db.insert_note_template(name, data["content"], current_app)
    return jsonify(message="Successful created or updated note template.")  

@bp.route("/artifacts/upload", methods=["POST"])
def upload_artifacts():
  project_name = request.args.get("project_name", None)
  if project_name is None:
    return abort(400, "Project name is required.")
  job_id = request.args.get("job_id", None)
  if job_id is None:
    return abort(400, "Job ID is required.")
  f = request.files["artifact"]
  if f is None:
    return abort(400, "Uploaded artifacts is required.")
  if os.path.splitext(f.filename)[1] != '.gz':
    return "Artifacts were not *.tar.gz file and would not be untarred."
  upload_path = os.path.join(get_info("UPLOAD_PATH"), project_name, job_id)
  try:
    os.makedirs(upload_path)
  except OSError:
    pass
  source_path = os.path.join(upload_path, secure_filename(f.filename))
  current_app.logger.debug("Save uploaded file to upload path: %s", source_path)
  f.save(source_path)
  current_app.logger.debug("Untar source file: %s", source_path)
  dest_path = os.path.join(get_info("DEPLOY_PATH"), project_name, job_id)
  target_path = os.path.join(dest_path)
  try:
    os.makedirs(target_path)
  except OSError:
    pass
  current_app.logger.debug("Untar artifacts to: %s", target_path)
  with tarfile.open(source_path) as tf:
    tf.extractall(target_path)
  return "Successful uploaded and processed artifacts."

@bp.route("/store", methods=["POST", "GET", "DELETE"])
def store():
  category = request.args.get("category")
  if not category:
    return abort(400, "Category is required.")
  try:
    if request.method == "POST":
      store = request.get_json()
      if not store:
        return abort(400, "Request body is required.")
      KeeperManager.add_to_store(category, store, current_app)
      return jsonify(message="Successful added or updated item to store.")
    elif request.method == "DELETE":
      KeeperManager.remove_from_store(category, current_app)
      return jsonify(message="Successful removed item from store.")
    elif request.method == "GET":
      return jsonify(KeeperManager.get_from_store(category, current_app))
  except KeeperException as e:
    return abort(e.code, "Failed to manipulate store: %s"% (e.message,))