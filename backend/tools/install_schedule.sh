#!/bin/bash
# 安装 / 卸载每日定时任务（macOS launchd）。默认工作日 16:45（本机时区）运行 tools/daily.py。
#   tools/install_schedule.sh            安装（或更新）
#   tools/install_schedule.sh uninstall  卸载
#   MM_HOUR=17 MM_MINUTE=0 tools/install_schedule.sh   改时间
set -e
LABEL="com.moneymaker.daily"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
BACKEND="$(cd "$(dirname "$0")/.." && pwd)"
HOUR="${MM_HOUR:-16}"; MINUTE="${MM_MINUTE:-45}"

if [ "$1" = "uninstall" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "已卸载 $LABEL"
  exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents" "$BACKEND/data"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$BACKEND/.venv/bin/python</string>
    <string>$BACKEND/tools/daily.py</string>
  </array>
  <key>WorkingDirectory</key><string>$BACKEND</string>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
  </array>
  <key>StandardOutPath</key><string>$BACKEND/data/daily.log</string>
  <key>StandardErrorPath</key><string>$BACKEND/data/daily.err.log</string>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string></dict>
</dict>
</plist>
PL
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "已安装 $LABEL：工作日 $(printf '%02d:%02d' "$HOUR" "$MINUTE") 运行，日志在 $BACKEND/data/daily.log"
echo "手动跑一次：launchctl kickstart gui/$(id -u)/$LABEL"
