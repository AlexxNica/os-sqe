#!/usr/bin/env bash

curl -o /tmp/sshpass.rpm http://dl.fedoraproject.org/pub/epel/7/x86_64/s/sshpass-1.05-5.el7.x86_64.rpm
yum -y localinstall /tmp/sshpass.rpm

if ( ! which pip ); then
    curl -o /tmp/get-pip.py https://bootstrap.pypa.io/get-pip.py
    python /tmp/get-pip.py
fi
if ( ! which virtualenv ); then
    pip install virtualenv
fi

venv_dir=vts-venv
rm -rf $venv_dir
virtualenv --no-site-packages $venv_dir
source ${venv_dir}/bin/activate
pip install -r requirements.txt

ansible-playbook -i inventory init.yaml
deactivate