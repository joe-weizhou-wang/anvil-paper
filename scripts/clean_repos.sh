#!/bin/bash -eux

##################################################
# cleans all magma repos by removing any changes #
##################################################

cd $(git rev-parse --show-toplevel)/data
ROOT_DIR=$(pwd)

# clean all git repos and delete non-git targets
for target in magma/targets/*; do
  if [[ $target == *"sqlite3"* ]]; then
    rm -r $target/repo/* 
    continue
  fi
  pushd $target/repo
  git reset --hard && git clean -f 
  popd
done
