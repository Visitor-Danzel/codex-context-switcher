#!/bin/sh
# Explicit fixture-only checks: no broad discovery, no real configuration writes.
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_root"
test -f 'build/legacy-context-repair-candidate/Codex Context Switcher.app/Contents/Info.plist'
verification="$project_root/build/legacy-context-repair-candidate/verification"
mkdir -p "$verification"
for item in 'runtime_policy:emit-policy' 'maximum_context_policy:emit-maximum-policy' 'test_maximum_context_ui:test-maximum-ui' 'test_context_runtime_repair:test-runtime' 'test_legacy_repair_session:test-session'; do
 source_name=${item%%:*}
 binary_name=${item#*:}
 clang -fobjc-arc -Wall -Wextra -Werror -Wno-unused-function -Wno-deprecated-declarations -Wno-arc-performSelector-leaks -mmacosx-version-min=13.0 \
  -I Sources/CodexContextCore -I Sources/CodexContextSwitcherApp -I Sources/LiveMonitorApp \
  "Tests/$source_name.m" Sources/CodexContextCore/CodexContextCore.m Sources/CodexContextSwitcherApp/ContextRepairSession.m \
  -framework Cocoa -framework Foundation -o "$verification/$binary_name"
done
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PYTEST'
import sys, unittest
sys.path.insert(0,'Tests')
names=['test_model_context_settings','test_model_context_worker',
       'test_context_settings_config','test_context_settings_preview',
       'test_context_settings_transaction','test_context_settings_restart',
       'test_maximum_context_package','test_maximum_context_guard','test_legacy_repair_integration']
# Two historical checks deliberately read live state or assume Codex is running.
# Fixture-only release verification excludes them explicitly, not as silent skips.
excluded={'test_live_closed_check_never_assumes_success_on_unknown_process',
          'test_normal_status_reads_configuration_instead_of_legacy_drafts'}
def cases(suite):
 for item in suite:
  if isinstance(item,unittest.TestSuite):yield from cases(item)
  else:yield item
suite=unittest.TestSuite(t for name in names for t in cases(unittest.defaultTestLoader.loadTestsFromName(name)) if t._testMethodName not in excluded)
result=unittest.TextTestRunner(verbosity=1).run(suite)
if result.skipped:raise SystemExit('Unexpected skipped verification')
raise SystemExit(0 if result.wasSuccessful() else 1)
PYTEST
"$verification/test-runtime"
"$verification/test-session"
"$verification/test-maximum-ui"
codesign --verify --deep --strict 'build/legacy-context-repair-candidate/Codex Context Switcher.app'
