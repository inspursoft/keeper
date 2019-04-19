insert into user (user_id, username, token) values (2, 'user1', '_WxM9xrRmBCBcfX_Xwaz');
insert into project (project_id, project_name) values (17, 'sso-combine-snapshot');
insert into user_project (user_id, project_id) values (2, 17);
insert into runner (runner_id, runner_tag) values(46, 'vagrant-vm-1');
insert into project_runner (project_id, vm_id, runner_id) values (17, '85f4a26', 46);
insert into vm (vm_id, vm_name, target, keeper_url) values ('85f4a26', 'gitlab-runner-1', 'vagrant'), ('minikube', 'minikube', 'minikube', '10.164.17.12:5000');
insert into vm_snapshot (vm_id, snapshot_name) values ('85f4a26', 'sn-04171559'), ('minikube', 'Snapshot-04160846');