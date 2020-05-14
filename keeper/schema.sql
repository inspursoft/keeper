drop table if exists user;
drop table if exists user_project;
drop table if exists runner;
drop table if exists project;
drop table if exists project_runner;
drop table if exists vm;
drop table if exists vm_snapshot;

create table user (
  id integer primary key autoincrement,
  user_id integer unique not null,
  username text unique not null,
  token text not null
);


create table project (
  id integer primary key autoincrement,
  project_id integer unique not null,
  project_name text not null,
  runner_token text
);

create table runner (
  id integer primary key autoincrement,
  runner_id integer unique not null,
  runner_name text not null
);

create table user_project (
  user_id integer not null,
  project_id integer not null
);

create table user_issue (
  user_id integer not null,
  issue_hash text not null
);

create table project_runner (
  project_id integer not null,
  vm_id text not null,
  runner_id integer not null
);

create table vm (
  id integer primary key autoincrement,
  vm_id text unique not null,
  vm_name text not null,
  target text not null,
  keeper_url text not null
);

create table vm_snapshot (
  id integer primary key autoincrement,
  vm_id text unique not null,
  snapshot_name text not null
);

create table note_template (
  id integer primary key autoincrement,
  template_name text unique not null,
  template_content text
);

create table ip_provision (
  id integer primary key autoincrement,
  ip_address text unique not null,
  is_allocated integer default 0
);

create table ip_runner (
  ip_provision_id integer not null,
  project_id integer not null,
  runner_id integer,
  pipeline_id integer not null,
  is_power_on integer not null default 0,
  is_canceled integer not null default 0
);

create table store (
	category varchar(50) not null,
	item_key text not null,
	item_val text,
	primary key (category, item_key)
);

ALTER TABLE project ADD priority INTEGER DEFAULT 3;

create table job_log_judgement (
  rule_name varchar(50) primary key ,
  rule text
);

create table evaluation (
  category varchar(50) primary key,
  standard text not null,
  level integer not null default 1,
  suggestion text
);