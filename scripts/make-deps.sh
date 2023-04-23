#!/bin/bash

for folder in $(ls -d ${WORKDIR:-${PWD}}/services/* | grep -v __pycache__)
do
    if [[ -d ${folder} ]]; then
        group=$(basename ${folder})
        if [[ $(poetry show --only=${group}) ]]; then
            echo creating requirements in ${folder}
            poetry export --without-hashes --with=${group} > ${folder}/requirements.txt
        fi
    fi
done
