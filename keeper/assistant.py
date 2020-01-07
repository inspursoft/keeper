from flask import (
  Blueprint, abort, request, current_app, jsonify, url_for
)

from keeper.manager import *
from werkzeug.utils import secure_filename
import tarfile
from urllib.parse import urljoin
import time

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

@bp.route("/release", methods=["POST"])
def release():
  operator = request.args.get("operator")
  if not operator:
    return abort(400, "Operator is required.")
  release_branch = request.args.get("release_branch")
  if not release_branch:
    return abort("Release branch is required.")
  release_repo = request.args.get("release_repo")
  if not release_repo:
    return abort(400, "Release repo is required.")
  version_info = request.args.get("version_info")
  if not version_info:
    return abort(400, "Version info is required.")
  category = request.args.get("category")
  if not category:
    return abort(400, "Category is required.")
  project = KeeperManager.resolve_project(operator, release_repo, current_app)
  project_id = project.project_id
  try:
    KeeperManager.create_branch(project_id, version_info, release_branch, current_app)
  except KeeperException as ke:
    current_app.logger.error(ke)
  def prepare_actions(action):
    actions = []
    actions.append({"action": action, "file_path": "install.md", "content": KeeperManager.resolve_action_from_store(category, ".md", current_app)})
    actions.append({"action": action, "file_path": "install.sh", "content": KeeperManager.resolve_action_from_store(category, ".sh", current_app)})
    return actions
  message = ""
  try:
    KeeperManager.commit_files(project_id, version_info, "Release for %s" % (version_info,), prepare_actions("create"), current_app)
    message = "Successful release to the repo: %s with branch: %s and version: %s" % (release_repo, release_branch, version_info)
    current_app.logger.debug(message)
  except KeeperException as ke:
    try:
      KeeperManager.commit_files(project_id, version_info, "Release for %s" % (version_info,), prepare_actions("update"), current_app)
      message = "Retried to release repo: %s to the branch: %s and version: %s with another update action" % (release_repo, release_branch, version_info)
    except KeeperException as ke:
      message = "Failed to release repo: %s" % (release_repo,)
      current_app.logger.error(message)
  return message

@bp.route("/variables", methods=["POST"])
def config_variables():
  config_repo = request.args.get("config_repo", None)
  if not config_repo:
    return abort(400, "Config repo name is required.")
  target_repo = request.args.get("target_repo", None)
  if not target_repo:
    return abort(400, "Target repo name is required.")
  operator = request.args.get("operator", None)
  if not operator:
    return abort(400, "Operator name is required.")
  file_path = request.args.get("file_path", None)
  if not file_path:
    return abort(400, "File path is required.")
  branch = request.args.get("branch", None)
  if not branch:
    branch = "master"
  try:
    config_project = KeeperManager.resolve_project(operator, config_repo, current_app)
  except KeeperException as e:
    current_app.logger.error("Failed to retrieve config repo: %s", e.message)
    return abort(401, "Unauthorized to access config repo: %s with operator %s" % (config_repo, operator))
  try:
    target_project = KeeperManager.resolve_project(operator, target_repo, current_app)
  except KeeperException as e:
    current_app.logger.error(e.message)
    return abort(e.code, e.message)
  try:
    config_project_id = config_project.project_id
    current_app.logger.debug("Config variable from the repository: %s at branch %s with file: %s, operator: %s", config_repo, branch, file_path, operator)
    target_project_id = target_project.project_id
    current_app.logger.debug("Set variable to the repository: %s", target_project.project_name)
    KeeperManager.resolve_config_variables(config_project_id, target_project_id, file_path, branch, current_app)
    return "Successful resolved config variables to the target repo."
  except KeeperException as e:
    current_app.logger.debug("Failed to handle config variables: %s", e)
    return abort(e.code, e.message)
