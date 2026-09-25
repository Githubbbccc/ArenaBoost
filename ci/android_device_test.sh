#!/usr/bin/env bash
# Runs the real-device integration tests and grants runtime permissions as soon
# as the app gets installed (DND access + "Modify system settings" + overlay).
set -u
PKG=com.arena.arenaboost

# Pre-build so a native (Kotlin/gradle) compile failure is surfaced here,
# clearly separated from emulator/test failures (as CI annotations).
set +e
flutter build apk --debug > /tmp/prebuild.log 2>&1
RC=$?
if [ $RC -ne 0 ]; then
  ERR=$(grep -E "^e: |error:|FAILURE:|What went wrong|Execution failed|Caused by" /tmp/prebuild.log | head -40)
  [ -z "$ERR" ] && ERR=$(tail -n 40 /tmp/prebuild.log)
  echo "$ERR" | while IFS= read -r l; do echo "::error::$l"; done
  exit $RC
fi

( for i in $(seq 1 240); do
    adb shell cmd notification allow_dnd $PKG >/dev/null 2>&1
    adb shell appops set $PKG WRITE_SETTINGS allow >/dev/null 2>&1
    adb shell appops set $PKG SYSTEM_ALERT_WINDOW allow >/dev/null 2>&1
    sleep 1
  done ) &
GRANTER=$!

set +e
flutter test integration_test -d emulator-5554 --reporter expanded > /tmp/itest.log 2>&1
RC=$?
set -u
if [ $RC -ne 0 ]; then
  ERR=$(grep -E "\[E\]|FAILED|Expected:|Actual:|Exception|Error:" /tmp/itest.log | head -40)
  [ -z "$ERR" ] && ERR=$(tail -n 40 /tmp/itest.log)
  echo "$ERR" | while IFS= read -r l; do echo "::error::$l"; done
fi
kill $GRANTER 2>/dev/null
exit $RC
