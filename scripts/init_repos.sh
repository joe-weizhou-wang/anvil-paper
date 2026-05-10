#!/bin/bash -eux

##################################################
# inits modules, clones magma targets and utils, #
# builds all repos, and finally applies patches  #
##################################################

cd $(git rev-parse --show-toplevel)/data
ROOT_DIR=$(pwd)

# init magma submodule if not already done
if [ $(ls magma | wc -l) -lt 1 ]; then
  pushd magma
  git submodule init
  git submodule update
  popd
fi

# clone each target
for target in magma/targets/*; do
  pushd $target
  OUT=. TARGET=. ./fetch.sh
  popd
done

if [ ! -d utils/unifdef-2.12 ]; then
  pushd utils
  wget https://dotat.at/prog/unifdef/unifdef-2.12.tar.gz
  tar -xvzf unifdef-2.12.tar.gz
  popd
fi
pushd utils/unifdef-2.12
make
popd

# apply bug patches for each target
for target in magma/targets/*; do
  pushd $target
  # iterate over all patches and apply them
  find "./patches/setup" "./patches/bugs" -name "*.patch" | \
  while read patch; do
      echo "Applying $patch"
      name=${patch##*/}
      name=${name%.patch}
      sed "s/%MAGMA_BUG%/$name/g" "$patch" | patch -p1 -d "./repo"
  done
  popd
done
