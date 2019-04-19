#!/bin/bash
minikube stop
VBoxManage snapshot $1 restore $2
minikube start
