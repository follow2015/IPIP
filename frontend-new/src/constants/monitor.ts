/**
 * 监控模块共享常量。
 * P1 修复：原 ALERT_TYPE_LABEL / ALERT_TYPE_COLOR 在 Overview 和 Alerts 两个文件重复定义，
 * 抽到 constants/monitor.ts 共享。
 */

export const ALERT_TYPE_LABEL: Record<string, string> = {
  device_unreachable: '设备不可达',
  device_recovered: '设备恢复',
  temperature_alert: '温度告警',
  disk_failure_alert: '硬盘故障',
  port_status_changed: '端口状态变化',
  monitor_interrupted: '监控中断',
  raid_failure_alert: 'RAID故障'
};

export const ALERT_TYPE_COLOR: Record<string, string> = {
  device_unreachable: 'red',
  device_recovered: 'green',
  temperature_alert: 'volcano',
  disk_failure_alert: 'red',
  port_status_changed: 'purple',
  monitor_interrupted: 'orange',
  raid_failure_alert: 'magenta'
};
