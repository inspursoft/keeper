from flask import (
  Blueprint, abort, request, current_app, jsonify, url_for
)

from keeper.manager import *
from werkzeug.utils import secure_filename
import tarfile
from urllib.parse import urljoin, quote
import time
import threading

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
      key = request.args.get("key", None)
      if key:
        return KeeperManager.get_from_store_by_key(category, key, current_app)
      return jsonify(KeeperManager.get_from_store(category, current_app))
  except KeeperException as e:
    return abort(e.code, "Failed to manipulate store: %s"% (e.message,))

@bp.route("/release/<action>", methods=["POST"])
def release(action):
  operator = request.args.get("operator", None)
  if not operator:
    return abort(400, "Operator is required.")
  release_branch = request.args.get("release_branch", None)
  if not release_branch:
    return abort("Release branch is required.")
  release_repo = request.args.get("release_repo", None)
  if not release_repo:
    return abort(400, "Release repo is required.")
  version_info = request.args.get("version_info", None)
  if not version_info:
    return abort(400, "Version info is required.")
  project_name = request.args.get("project_name", None)
  if not project_name:
    project_name = "N/A"
  version = request.args.get("version", None)
  if not version:
    version = "N/A"
  category = request.args.get("category", None)
  if not category:
    return abort(400, "Category is required.")
  project = KeeperManager.resolve_project(operator, release_repo, current_app)
  project_id = project.project_id
  try:
    KeeperManager.create_branch(project_id, version_info, release_branch, current_app)
  except KeeperException as ke:
    current_app.logger.error(ke)
  try:
    actions = []
    actions.append({"action": action, "file_path": "install.md", "content": KeeperManager.resolve_action_from_store(category, ".md", current_app)})
    actions.append({"action": action, "file_path": "install.sh", "content": KeeperManager.resolve_action_from_store(category, ".sh", current_app, project_name, version)})
    KeeperManager.commit_files(project_id, version_info, "Commit files to release", actions, current_app)
    message = "Successful released to the repo: %s with branch: %s" % (release_repo, version_info)
    current_app.logger.debug(message)
    return message
  except KeeperException as ke:
    message = "Failed to commit files to the repository: %s" % (release_repo,)
    current_app.logger.error(message)
    return abort(400, message)
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

@bp.route("/files", methods=["GET", "POST", "PUT"])
def resolve_repo_files():
  username = request.args.get("username", None)
  if not username:
    return abort(400, "Username is required.")
  project_name = request.args.get("project_name", None)
  if not project_name:
    return abort(400, "Project name is required.")
  file_path = request.args.get("file_path", None)
  if not file_path:
    file_path = ".gitlab-ci.yml"
  branch = request.args.get("branch", None)
  if not branch:
    branch = "master"
  current_app.logger.debug("Retrieve files: %s from project: %s at branch: %s", file_path, project_name, branch)
  try:
    if request.method == "GET":
      content = KeeperManager.retrieve_files_from_repo(username, project_name, file_path, branch, current_app)
      return jsonify(content=content)
    else:
      data = request.get_json()
      if not data:
        return abort(400, "Missing request data in body.")
      if "content" not in data:
        return abort(400, "Request data is missing content.")
      content = data["content"]
      action = ""
      if request.method == "POST":
        action = "create"
      elif request.method == "PUT":
        action = "update"
      KeeperManager.commit_file_to_repo(username, project_name, action, file_path, branch, content, current_app)
      return "Successful %s file: %s to the branch: %s to the project: %s" % (action, file_path, branch, project_name)
  except KeeperException as e:
    current_app.logger.debug("Failed to retrieve files: %s", e)
    return abort(e.code, e.message)

@bp.route("/jobs/failure", methods=["POST"])
def resolve_pipeline_failed_jobs():
  base_username = request.args.get("base_username", None)
  if not base_username:
    return abort(400, "Base repo username is required.")
  base_project_name = request.args.get("base_project_name", None)
  if not base_project_name:
    return abort(400, "Base project name is required.")
  pipeline_project_id = request.args.get("pipeline_project_id", None)
  if not pipeline_project_id:
    return abort(400, "Pipeline Project ID is required.")
  pipeline_id = request.args.get("pipeline_id", None)
  if not pipeline_id:
    return abort(400, "Pipeline ID is required.")
  try:
    pipeline_logs = KeeperManager.get_pipeline_failed_jobs(int(pipeline_project_id), int(pipeline_id), current_app)
    matched, assignee_info = KeeperManager.match_job_log_by_judgement(pipeline_logs, current_app)
    if matched:
      current_app.logger.debug("No matched with judgement rule for DevOps issue of characters, will open issue to developer as assignee...")
      open_issue_url = urljoin("http://localhost:5000", url_for("integration.issue_assign", username=base_username, project_name=base_project_name))
      current = current_app._get_current_object()
      def callback():
        issue_title = "Issue for pipeline: %d" % (assignee_info["pipeline_id"],)
        issue_description = "There was some error occurred when executing pipeline: %d for job: %s that might be caused by your misconfiguration or code." % (assignee_info["pipeline_id"], assignee_info["job_name"])
        resp = requests.post(open_issue_url, json={"assignee": assignee_info["assignee"], "title": issue_title, "description": issue_description})
        current.logger.debug("Requested URL: %s with status code: %d, response text: %s" % (open_issue_url, resp.status_code, resp.text))
      threading.Thread(target=callback).start()
    return jsonify(message="Successful resolved pipeline failed jobs.")
  except KeeperException as e:
    current_app.logger.error("Failed to resolve artifacts: %s", e)
    return abort(e.code, e.message)

@bp.route("/contents/evaluate", methods=["POST"])
def evaluate_content():
  category = request.args.get("category", None)
  if not category:
    return abort(400, "Category is required.")
  username = request.args.get("username", None)
  if not username:
    return abort(400, "Username is required.")
  project_name = request.args.get("project_name", None)
  if not project_name:
    return abort(400, "Project name is required.")
  file_path = request.args.get("file_path", None)
  if not file_path:
    return abort(400, "File path is required.")
  branch = request.args.get("branch", None)
  if not branch:
    branch = "master"
  try:
    content = KeeperManager.retrieve_files_from_repo(username, project_name, quote(file_path, safe=""), branch, current_app)
    evaluated, evaluation = KeeperManager.evaluate_content(category, content, current_app)
    if evaluated:
      return jsonify(category=evaluation.category, standard=evaluation.standard, level=evaluation.level, suggestion=evaluation.suggestion)
    return jsonify(message="Evaluation executed but matched no standard by category: %s" % (category,))
  except KeeperException as e:
    current_app.logger.error("Failed to evaluate content for file: %s with error: %s", file_path, e)
    return abort(e.code, e.message)


@bp.route("/jobs/judgement", methods=["POST", "DELETE"])
def create_or_update_job_log_judgement():
  current = current_app._get_current_object()
  def batch_save_callback(config_variables):
    KeeperManager.create_job_log_judgement_from_dict(config_variables, current)
  def save_callback():
    data = request.get_json()
    if not data:
      return abort(400, "Missing request body.")
    if "rule_name" not in data:
      return abort(400, "Rule name is required.")
    if "rule" not in data:
      data["rule"] = ""
    KeeperManager.create_job_log_judgement(data["rule_name"], data["rule"], current)
  def remove_callback():
    rule_name = request.args.get("rule_name", None)
    if not rule_name:
      return abort(400, "Rule name is required.")
    KeeperManager.remove_job_log_judgement(rule_name, current)
  return create_or_update_action(request, current, "job log judgement", batch_save_callback, save_callback, remove_callback)

@bp.route("/evaluations", methods=["POST", "DELETE"])
def create_or_update_evaluation():
  current = current_app._get_current_object()
  def batch_save_callback(config_variables):
    KeeperManager.create_evaluation_from_dict(config_variables, current)
  def save_callback():
    data = request.get_json()
    if not data:
      return abort(400, "Missing request body.")
    if "category" not in data:
      return abort(400, "Category is required.")
    if "standard" not in data:
      return abort(400, "Standard is required.")
    if "level" not in data:
      data["level"] = 1
    if "suggestion" not in data:
      data["suggestion"] = ""
    evaluation = Evaluation(data["category"], data["standard"], data["level"], data["suggestion"])
    KeeperManager.create_evaluation(evaluation, current)
  def remove_callback():
    category = request.args.get("category", None)
    if not category:
      return abort(400, "Category is required.")
    KeeperManager.remove_evaluation(category, current)
  return create_or_update_action(request, current, "evaluation", batch_save_callback, save_callback, remove_callback)

def create_or_update_action(request, current, identity, batch_save_callback, save_callback, remove_callback):
  if request.method == "POST":
    from_file = request.args.get("from_file", None)
    if from_file:
      username = request.args.get("username", None)
      if not username:
        return abort(400, "Username is required when get %s from file." % (identity,))
      project_name = request.args.get("project_name", None)
      if not project_name:
        return abort(400, "Project name is required when get %s from file." % (identity,))
      branch = request.args.get("branch", None)
      if not branch:
        branch = "master"
      try:
        project = KeeperManager.resolve_project(username, project_name, current)
        config_variables = KeeperManager.resolve_key_value_pairs_from_file(project.project_id, branch, from_file, current)
        batch_save_callback(config_variables)
        return jsonify(message="Successful config %s from file: %s with project: %s" % (identity, from_file, project.project_name))
      except KeeperException as e:
        current.logger.error("Failed to resolve %s from file: %s", identity, e)
        return abort(e.code, e.message)
    else:     
      try:
        save_callback()
        return jsonify(message="Successful maintained %s." % (identity,))
      except KeeperException as e:
        current.logger.error("Failed to maintain %s with error: %s", identity, e)
        return abort(e.code, e.message)
  elif request.method == "DELETE":
    try:
      remove_callback()
      return jsonify(message="Successful removed %s" % (identity,))
    except KeeperException as e:
      current.logger.error("Failed to remove %s with error: %s", identity, e)
      return abort(e.code, e.message)