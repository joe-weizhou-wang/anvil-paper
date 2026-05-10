#!/bin/bash

apt-get update && \
    apt-get install -y git make autoconf automake libtool bison re2c pkg-config \
        libicu-dev build-essential libxml2-dev libsqlite3-dev libc++-dev libc++abi-dev libstdc++6
