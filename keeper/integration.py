from flask import (
  Blueprint, current_app, jsonify, url_for, abort, request
)

import os
from urllib.parse import urljoin

from keeper import get_info

from keeper.manager import *
from keeper.model import *
from keeper.vm import recycle_vm

import queue
import time
import threading
import requests

bp = Blueprint("integration", __name__ ,url_prefix="/api/v1")

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
  if "description" not in data:
    data["description"] = "As title."
  if "label" not in data:
    data["label"] = "issue"

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
  current_app.logger.debug(data)
  
  project = data["project"]
  project_id = project["id"]
  project_name = project["name"]
  object_attr = data["object_attributes"]
  action = object_attr["action"]
  issue_iid = object_attr["iid"]
  title = object_attr["title"]
  labels = data["labels"]
  created_at = object_attr["created_at"]
  issue_title = 'issue as branch'
  
  if action not in ["open"]:
    message = "Bypass for inrelevant action: %s in openning issue." % (action,)
    current_app.logger.debug(message)
    return message

  if title.find("Follow-up from") >= 0:
    message = "Bypass for automatic generated issue with title: %s" % (title,)
    current_app.logger.debug(message)
    return message
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
    assignee = User.new()
    if not assignee_id:
      assignee = KeeperManager.resolve_user(default_assignee, current_app)
      assignee_id = assignee.user_id
    if not milestone_id:
      milestones = KeeperManager.get_all_milestones(project_id, {"state": "active"}, current_app) 
      if len(milestones) == 0:
        current_app.logger.error("No active milestones found with project ID: %d" % (project_id))
      else:
        milestone_id = milestones[-1]["id"]
        KeeperManager.update_issue(project_id, issue_iid, {"assignee_ids": [assignee.user_id], "milestone_id": milestone_id}, current_app)
    try:
      due_date = KeeperManager.resolve_due_date(created_at, labels, current_app)
      KeeperManager.update_issue(project_id, issue_iid, {"due_date": due_date}, current_app)
    except KeeperException as ke:
      current_app.logger.error(ke)

    KeeperManager.create_branch_per_assignee(project_name, assignee_id, branch_name, ref, current_app)
    return jsonify(message="Successful created branch: %s per assignee ID: %d" % (branch_name, assignee_id))
  except KeeperException as e:
    current_app.logger.error(e)
    return abort(e.code, e.message)

q = queue.PriorityQueue()

@bp.route("/runners/probe")
def runner_probe():
  project_id = request.args.get("project_id", None)
  if not project_id:
    return abort(400, "Project ID is required.")
  vm_name = request.args.get("vm_name", None)
  if not vm_name:
    return abort(400, "VM name is required.")
  status = request.args.get("status", None)
  if not status:
    return abort(400, "Status is required.")
  while not q.empty():
    try:
      pipeline_task = q.get()
      pipeline_id = pipeline_task.id
      current_app.logger.debug("Got pipeline ID: %d from queue with priority: %d", pipeline_id, pipeline_task.priority)
      try:
        KeeperManager.retry_pipeline(int(project_id), pipeline_id, current_app)
      except KeeperException as e:
        current_app.logger.error(e.message)
    except KeeperException as e:
      current_app.logger.debug("Waiting for release IP to retry pipelines ...")
    time.sleep(5)
  return "None of queued pipelines."

@bp.route("/runners", methods=["POST"])
def prepare_runner():
  base_repo_name = request.args.get("base_repo_name", None)
  if not base_repo_name:
    return abort(400, "Base repo name is required.")
  username = request.args.get("username", None)
  if not username:
    return abort(400, "Username is required.")
  
  data = request.get_json()
  current_app.logger.debug(data)
  project = data["project"]
  abbr_name = project["name"]
  project_name = project["path_with_namespace"]
  project = KeeperManager.resolve_project(username, project_name, current_app)
  if not project:
    return abort(400, "Project name: %s does not exist." % (project_name,))
  project_id = project.project_id
  object_attr = data["object_attributes"]
  pipeline_id = object_attr["id"]
  status = object_attr["status"]
  vm_base_name = "%s-runner-%s" % (abbr_name, base_repo_name)
  vm_name = "%s-%d" % (vm_base_name, pipeline_id)
  current = current_app._get_current_object()
  probe_request_url = urljoin("http://localhost:5000", url_for(".runner_probe", project_id=project_id, vm_name=vm_name, status=status))
  def callback():
    resp = requests.get(probe_request_url)
    current.logger.debug("Requested URL: %s with status code: %d" % (probe_request_url, resp.status_code))
  threading.Thread(target=callback).start()
  if status in ["success", "canceled", "failed"]:
    current_app.logger.debug("Runner mission is %s will be removing it...", status)
    recycle_vm(current_app, vm_name, project_id, pipeline_id, status)
  if KeeperManager.get_ip_provision_by_pipeline(pipeline_id, current_app):
    current_app.logger.debug("VM would not be re-created as the pipeline is same with last one.")
    return jsonify(message="VM would not be re-created as the pipeline is same with last one.")
  if status not in ["running", "pending"]:
    current_app.logger.debug("Runner would not be prepared as the pipeline is %s.", status) 
    return jsonify(message="Runner would not be prepared as the pipeline is %s" % (status,))
  try:
    ip_provision = KeeperManager.get_ip_provision(project_id, current_app)
    KeeperManager.reserve_ip_provision(ip_provision.id, current_app)
    KeeperManager.register_ip_runner(ip_provision.id, pipeline_id, project_id, current_app)
  except KeeperException as e:
    current_app.logger.error(e.message)
    KeeperManager.cancel_pipeline(project_id, pipeline_id, current_app)
    if not KeeperManager.get_ip_provision_by_pipeline(pipeline_id, current_app):
      project = KeeperManager.resolve_project_with_priority(username, project_name, current_app)
      current_app.logger.debug("Pipeline: %d has queued for executing with priority: %d", pipeline_id, project.priority)
      q.put(PipelineTask(pipeline_id, project.priority))
    return abort(e.code, e.message)
  current_app.logger.debug("Runner with pipeline: %d status is %s, with IP provision ID: %d, IP: %s", pipeline_id, status, ip_provision.id, ip_provision.ip_address)
  try:
    vm_conf = {
      "vm_box": get_info("VM_CONF")["VM_BOX"],
      "vm_memory": get_info("VM_CONF")["VM_MEMORY"],
      "vm_ip": ip_provision.ip_address,
      "runner_name": vm_name,
      "runner_tag": "%s-vm" % (vm_base_name)
    }
    request_url = urljoin("http://localhost:5000", url_for("vm.vm", name=vm_name, username=username, project_id=project_id, project_name=project_name, status=status))
    resp = requests.post(request_url, json=vm_conf, params={"ip_provision_id": ip_provision.id, "pipeline_id": pipeline_id})
    message = "Requested URL: %s with status code: %d" % (request_url, resp.status_code)
    current_app.logger.debug(message)
    return message
  except Exception as e:
    current_app.logger.error("Failed to prepare runner: %s", e)
    return abort(500, e)

@bp.route("/runners/register", methods=["POST", "DELETE"])
def register_runner():
  username = request.args.get("username", None)
  if not username:
    return abort(400, "Username is required.")
  project_name = request.args.get("project_name", None)
  if not project_name:
    return abort(400, "Project name is required.")
  try:
    if request.method == "POST":
      config = request.get_json()
      if not config:
        return abort(400, "Runner config is required.")
      if "runner_token" not in config:
        return abort(400, "Runner token is required.")
      KeeperManager.register_runner(username, project_name, config, current_app)
      message = "Successful registered runner."
      current_app.logger.debug(message)
      return message
    elif request.method == "DELETE":
      KeeperManager.unregister_runner(username, project_name, current_app)
      message = "Successful unregistered runner."
      current_app.logger.debug(message)
      return message
  except KeeperException as e:
    current_app.logger.error("Failed to register runner: %s", e)
    return abort(500, e)
  
@bp.route("/merge-request/relate-issue", methods=["POST"])
def relate_issue_to_merge_request():
  data = request.get_json()
  current_app.logger.debug(data)
  project = data["project"]
  object_attr = data["object_attributes"]
  project_id = project["id"]
  merge_request_id = object_attr["iid"]
  state = object_attr["state"]
  source = object_attr["source"]
  target = object_attr["target"]

  if state not in ["opened"]:
    message = "No need to relate issue as current state is %s" % (state,)
    current_app.logger.debug(message)
    return message
  if source["id"] == target["id"]:
    message = "No need to relate issue as same repos."
    current_app.logger.debug(message)
    return message
  try:
    KeeperManager.create_discussion_to_merge_request(project_id, merge_request_id, "Start to discuss...", current_app)
    message = "Successful related issue to merge request."
    current_app.logger.debug(message)
    return message
  except KeeperException as e:
    current_app.logger.error("Failed to relate issue to merge request: %s", e)
    return abort(e.code, e.message)

@bp.route("/merge-request/pre-merge", methods=["POST"])
def legacy_pre_merge():
  trigger_token = request.args.get("token", None)
  if not trigger_token:
    return abort(400, "Trigger token is required.")
  data = request.get_json()
  current_app.logger.debug(data)
  object_attr = data["object_attributes"]
  action = object_attr["action"]
  if action not in ["open", "reopen", "update"]:
    current_app.logger.debug("Bypass to trigger pre-merge request as its action was %s.", action)
    return "Bypass to trigger pre-merge request as its action was %s." % (action,)
  target = object_attr["target"]
  target_url = target["git_http_url"]
  target_project_id = object_attr["target_project_id"]
  target_branch = object_attr["target_branch"]
  user = data["user"]
  username = user["username"]
  email = "%s@inspur.com" % (username,)
  try:
    db_user = KeeperManager.resolve_user(username, current_app)
    params = {
      "CI_MERGE_REQUEST_PROJECT_URL": target_url,
      "CI_MERGE_REQUEST_TARGET_BRANCH_NAME": target_branch,
      "CI_TOKEN": db_user.token,
      "GITLAB_USER_NAME": username,
      "GITLAB_USER_EMAIL": email
    }
    KeeperManager.trigger_legacy_pipeline(target_project_id, trigger_token, target_branch, params, current_app)
    return "Successful triggered pre-merge with pipeline."
  except KeeperException as e:
    current_app.logger.debug("Failed to request pre-merge: %s", e)
    return abort(e.code, e.message)

@bp.route("/tag/release", methods=["POST"])
def tag_release():
  release_repo = request.args.get("release_repo", None)
  if not release_repo:
    return abort(400, "Release repo is required.")
  release_branch = request.args.get("release_branch", None)
  if not release_branch:
    return abort(400, "Release branch is required.")
  username = request.args.get("username", None)
  if not username:
    return abort(400, "Username is required.")

  data = request.get_json()
  current_app.logger.debug(data)
  object_kind = data["object_kind"]
  current_app.logger.debug("Current object kind is %s", object_kind)

  checkout_sha = ""
  ref = ""
  version_info = ""
  if object_kind == "pipeline":
    object_attr = data["object_attributes"]
    if not object_attr["tag"]:
      current_app.logger.debug("Bypass for is not tag.")
      return "Bypass for pipeline is not tag."
    current_app.logger.debug("Handle pipeline with tag for release repo: %s, release branch: %s" % (release_repo, release_branch))
    checkout_sha = object_attr["sha"]
    ref = object_attr["ref"]
    version_info = ref + "-as-branch"
  else:
    checkout_sha = data["checkout_sha"]
    ref = data["ref"]
    version_info = ref[ref.rindex("/") + 1:] + "-as-branch"

  if checkout_sha is None:
    current_app.logger.debug("Bypass for none of checkout SHA or ref.")
    return "Bypass for none of checkout SHA or ref."
  def request_with_action(action):
    current_app.logger.debug("Version info: %s", version_info)
    release_url = urljoin("http://localhost:5000", url_for("assistant.release", action=action, operator=username, release_repo=release_repo, release_branch=release_branch, category=checkout_sha, version_info=version_info))
    resp = requests.post(release_url)
    message = "Requested release URL: %s to create files, with status code: %s, and response content: %s" % (release_url, resp.status_code, resp.text)
    current_app.logger.debug(message)
    return message
  message = ""    
  try:
    message = request_with_action("create")
  except KeeperException as ke:
    if ke.code == 400:
      message = request_with_action("update")
    else:
      message = "Failed to request release URL with error: %s" % (ke.message,)
      current_app.logger.error(message)
  return message
    