#!/bin/bash

for folder in $(ls -d ${WORKDIR:-${PWD}}/services/* | grep -v __pycache__)
do
    if [[ -d ${folder} ]]; then
        group=$(basename ${folder})
        if [[ $(poetry show --with=${group} --without=dev) ]]; then
            echo creating requirements in ${folder}
            poetry export --without-hashes --with=${group} > ${folder}/requirements.txt
        fi
    fi
done

poetry export --without-hashes --with dev > ${WORKDIR:-${PWD}}/tests/requirements.txt
