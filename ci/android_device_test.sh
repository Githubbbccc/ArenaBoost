#!/usr/bin/env bash
# Runs the real-device integration tests and grants runtime permissions as soon
# as the app gets installed (DND access + "Modify system settings").
set -u
PKG=com.arena.arenaboost
( for i in $(seq 1 240); do
    adb shell cmd notification allow_dnd $PKG >/dev/null 2>&1
    adb shell appops set $PKG WRITE_SETTINGS allow >/dev/null 2>&1
    sleep 1
  done ) &
GRANTER=$!
flutter test integration_test -d emulator-5554 --reporter expanded
RC=$?
kill $GRANTER 2>/dev/null
exit $RC
