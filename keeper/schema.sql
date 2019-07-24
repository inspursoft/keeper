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
  project_name text not null
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