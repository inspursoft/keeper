from flask import (
  Blueprint, current_app, jsonify, url_for, abort, request
)

import os
from werkzeug.utils import secure_filename
import tarfile
from urllib.parse import urljoin

from keeper.manager import *
from keeper import get_info
import ast

import queue
import time
import threading

bp = Blueprint("integration", __name__ ,url_prefix="/api/v1")

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
  project_id = data["project"]["id"]
  object_attr = data["object_attributes"]
  source_project_id = object_attr['source_project_id']
  ref = object_attr["source_branch"]
  commit_id = object_attr["last_commit"]["id"]
  try:
    builds = KeeperManager.get_repo_commit_status(project_id, commit_id, current_app)
    for build in builds:
      if build['status'] == 'skipped':
        abort(422, "INFO: %s build skipped (reason: build %d is in \"%s\" status)" % (commit_id, build['id'], build['status']))
        return
    resp = KeeperManager.trigger_pipeline(source_project_id, ref, current_app)
    return jsonify(resp)
  except KeeperException as e:
    current_app.logger.error(e)
    return abort(e.code, e.message)

default_open_branch_prefix = 'fix:'
default_ref = 'dev'

@bp.route('/issue', methods=["POST"])
def issue():
  username = request.args.get('username', None)
  if username is None:
    return abort(400, "Username is required.")
  ref = request.args.get('ref', default_ref)
  open_branch_prefix = request.args.get('open_branch_prefix', default_open_branch_prefix)
  current_app.logger.info("Current ref branch is: %s", ref)
  current_app.logger.info("Current openning branch prefix is: %s", open_branch_prefix)
  data = request.get_json()
  if data is None:
    current_app.logger.error("None of request body.")
    return abort(400, "None of request body.")
  project = data['project']
  project_id = project['id']
  object_attr = data["object_attributes"]
  title = object_attr["title"]
  issue_iid = object_attr["iid"]

  s_title = title.lower()
  if not s_title.startswith(open_branch_prefix):
    current_app.logger.debug("No need to create branch with openning issue.")
    return jsonify(message="No need to create branch with openning issue.")

  try:
    branch_name = KeeperManager.resolve_branch_name(s_title[len(open_branch_prefix):])
    KeeperManager.create_branch(project_id, branch_name, ref, current_app)
    KeeperManager.comment_on_issue(username, project_id, issue_iid, "Branch: %s has been created." % (branch_name,), current_app)
    return jsonify(message="Successful created branch with issue.")
  except KeeperException as e:
    current_app.logger.error(e)
    return abort(e.code, e.message)

default_description = 'Assigned issue: %s to %s'
default_label = 'quality'
default_open_issue_prefix = "bug:"

@bp.route("/issues/assign", methods=["POST"])
def issue_assign():
  username = request.args.get('username', None)
  if username is None:
    return abort(400, "Username is required.")
  project_name = request.args.get('project_name', None)
  if project_name is None:
    return abort(400, "Project name is required.")
  data = request.get_json()
  if data is None:
    return abort(400, "Requested data is missing.")
  if "title" not in data:
    return abort(400, "Issue title is required.")
  if "assignee" not in data:
    return abort(400, "Issue assignee is required.")

  s_title = data['title'].lower()
  if not s_title.startswith(default_open_issue_prefix):
    current_app.logger.debug("No need to create issue to assignee as title is: %s", data['title'])
    return jsonify(message="No need to create issue to assignee as title is: %s" % data['title'])
  
  if "description" not in data:
    description = default_description % (data['title'], username)    
  if "label" not in data:
    label = default_label
  try:
    project = KeeperManager.resolve_project(username, project_name, current_app)
    KeeperManager.post_issue_to_assignee(project.project_id, data['title'], data['description'], data['label'], data['assignee'], current_app)
    return jsonify(message="Successful assigned issue to user: %s under project: %s" % (username, project_name))
  except KeeperException as e:
    current_app.logger.error(e)
    return abort(e.code, e.message)

@bp.route("/issues/per-sonarqube", methods=["POST"])
def issue_per_sonarqube():
  sonarqube_token = request.args.get("sonarqube_token", None)
  if sonarqube_token is None:
    return abort(400, "SonarQube token is required.")
  sonarqube_project_name = request.args.get("sonarqube_project_name", None)
  if sonarqube_token is None:
    return abort(400, "SonarQube project name is required.")
  severities = request.args.get("severities", "CRITICAL,BLOCKER")
  created_in_last = request.args.get("created_in_last", "10d")
  try:
    KeeperManager.post_issue_per_sonarqube(sonarqube_token, sonarqube_project_name, severities, created_in_last, current_app)
    return jsonify(message="Successful assigned issue to project: %s" % (sonarqube_project_name))
  except KeeperException as e:
    current_app.logger.error(e)
    return abort(e.code, e.message)

@bp.route("/issues/open-peer", methods=["POST"])
def issue_open_peer():
  ref = request.args.get('ref', None)
  if ref is None:
    return abort(400, "Default ref is required.")
  default_assignee = request.args.get('default_assignee', None)
  if default_assignee is None:
    return abort(400, "Default assignee is required.")
  
  data = request.get_json()
  project = data["project"]
  project_id = project["id"]
  project_name = project["name"]
  object_attr = data["object_attributes"]
  issue_iid = object_attr["iid"]
  issue_title = 'issue as branch'

  branch_name = KeeperManager.resolve_branch_name("{}-{}".format(issue_iid, issue_title), current_app)
  current_app.logger.debug("Create branch: %s with ref: %s", branch_name, ref)
  try:
    KeeperManager.get_branch(project_id, branch_name, current_app)
  except KeeperException as e:
    if e.code == 404:
      current_app.logger.debug("Creating branch: %s as it does not exists will create one.", branch_name)
      KeeperManager.create_branch(project_id, branch_name, ref, current_app)
    else:
      current_app.logger.error(e)
  try:
    assignee_id = object_attr["assignee_id"]
    milestone_id = object_attr["milestone_id"]
    if assignee_id is None or milestone_id is None:
      if assignee_id is None:
       assignee = KeeperManager.resolve_user(default_assignee, current_app)
       assignee_id = assignee["user_id"]
      if milestone_id is None:
        milestones = KeeperManager.get_all_milestones(project_id, {"state": "active"}, current_app) 
        if len(milestones) == 0:
          current_app.logger.error("No active milestones found with project ID: %d" % (project_id))
          return abort(404, "No active milestones found with project ID: %d" % (project_id))
        milestone_id = milestones[-1]["id"]
      KeeperManager.update_issue(project_id, issue_iid, {"assignee_ids": [assignee["user_id"]], "milestone_id": milestone_id}, current_app)
    KeeperManager.create_branch_per_assignee(project_name, assignee_id, branch_name, ref, current_app)
    return jsonify(message="Successful created branch: %s per assignee ID: %d" % (branch_name, assignee_id))
  except KeeperException as e:
    current_app.logger.error(e)
    return abort(e.code, e.message)

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

q = queue.Queue()

@bp.route("/runners/probe")
def runner_probe():
  project_id = request.args.get("project_id", None)
  if not project_id:
    return abort(400, "Project ID is required.")
  while not q.empty():
    try:
      ip_provision = KeeperManager.get_ip_provision(project_id, current_app)
      pipeline_id = q.get()
      current_app.logger.debug("Got pipeline ID: %d from queue.", pipeline_id)
      try:
        KeeperManager.retry_pipeline(int(project_id), pipeline_id, current_app)
      except KeeperException as e:
        current_app.logger.error(e.message)
    except KeeperException as e:
      current_app.logger.error("Waiting for release IP to retry pipelines ...")
    time.sleep(4)
  return "None of queued pipelines."

@bp.route("/runners", methods=["POST"])
def prepare_runner():
  data = request.get_json()
  current_app.logger.debug(data)
  project = data["project"]
  project_id = project["id"]
  object_attr = data["object_attributes"]
  pipeline_id = object_attr["id"]
  status = object_attr["status"]
  project_name = project["path_with_namespace"]
  builds = data["builds"]
  abbr_name = project["name"]
  username = data["user"]["name"]
  vm_base_name = "%s-runner-%s" % (abbr_name, username)
  vm_name = "%s-%d" % (vm_base_name, pipeline_id)
  
  probe_request_url = urljoin("http://localhost:5000", url_for(".runner_probe", project_id=project_id))
  def callback():  
    resp = requests.get(probe_request_url)
    message = "Requested URL: %s with status code: %d" % (probe_request_url, resp.status_code)
  threading.Thread(target=callback).start()

  if status in ["success", "canceled"]:
    current_app.logger.debug("Runner mission is %s will be removed it...", status)
    try:
      KeeperManager(current_app, vm_name).force_delete_vm()
    except KeeperException as e:
      current_app.logger.error(e.message)
    KeeperManager.unregister_runner_by_name(vm_name, current_app)
    KeeperManager.release_ip_runner_on_success(pipeline_id, current_app)
  if KeeperManager.get_ip_provision_by_pipeline(pipeline_id, current_app):
    current_app.logger.debug("VM would not be re-created as the pipeline is same with last one.")
    return jsonify(message="VM would not be re-created as the pipeline is same with last one.")
  if status not in ["running", "pending"]:
    current_app.logger.debug("Runner would not be prepared as the pipeline is %s.", status) 
    return jsonify(message="Runner would not be prepared as the pipeline is %s" % (status,))
  try:
    ip_provision = KeeperManager.get_ip_provision(project_id, current_app)
    KeeperManager.reserve_ip_provision(ip_provision.id, current_app)
  except KeeperException as e:
    current_app.logger.error(e.message)
    KeeperManager.cancel_pipeline(project_id, pipeline_id, current_app)
    q.put(pipeline_id)
    return abort(e.code, e.message)
  current_app.logger.debug("Runner with pipeline: %d status is %s, with IP provision ID: %d, IP: %s", pipeline_id, status, ip_provision.id, ip_provision.ip_address)
  try:
    vm_conf = {
      "vm_box": get_info("VM_CONF")["VM_BOX"],
      "vm_memory": get_info("VM_CONF")["VM_MEMORY"],
      "vm_ip": ip_provision.ip_address,
      "runner_name": vm_name,
      "runner_tag": "%s-vm" % (vm_base_name),
      "runner_token": KeeperManager.resolve_runner_token(username, project_name, current_app)
    }
    request_url = urljoin("http://localhost:5000", url_for("vm.vm", name=vm_name, username=username, project_name=project_name))
    resp = requests.post(request_url, json=vm_conf, params={"ip_provision_id": ip_provision.id, "pipeline_id": pipeline_id})
    message = "Requested URL: %s with status code: %d" % (request_url, resp.status_code)
    current_app.logger.debug(message)
    return message
  except Exception as e:
    current_app.logger.error("Failed to prepare runner: %s", e)
    return abort(500, e)