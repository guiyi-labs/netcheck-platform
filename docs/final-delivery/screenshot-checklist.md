# 论文截图清单

> 用于论文“系统实现”“系统测试”“运行效果”章节配图。

## 页面截图

| 编号 | 页面 | 地址 | 截图用途 |
|---|---|---|---|
| S01 | 登录页 | http://localhost:8080/login.html | 系统登录与鉴权 |
| S02 | 仪表盘 | http://localhost:8080/index.html | 系统总览、趋势、告警统计 |
| S03 | 资产管理 | http://localhost:8080/assets.html | 资产台账管理 |
| S04 | 巡检任务 | http://localhost:8080/tasks.html | 任务配置、检测类型、定时巡检 |
| S05 | 运行详情 | http://localhost:8080/task-run.html | 单次巡检执行过程 |
| S06 | 巡检结果 | http://localhost:8080/results.html | 结果留痕和筛选 |
| S07 | 故障诊断 | http://localhost:8080/diagnosis.html | 自动诊断和处理建议 |
| S08 | 告警中心 | http://localhost:8080/alerts.html | 告警确认、恢复、策略配置 |
| S09 | 报告管理 | http://localhost:8080/reports.html | 报告生成与下载 |
| S10 | 资产发现 | http://localhost:8080/discovery.html | 授权范围资产发现 |
| S11 | 逻辑拓扑 | http://localhost:8080/topology.html | 网络逻辑拓扑展示 |
| S12 | Excel 报告 | 下载后的 xlsx 文件 | 巡检报告内容 |

## 建议截图顺序

1. 登录页。
2. 仪表盘总览。
3. 资产管理列表。
4. 巡检任务配置，突出 Ping/端口/HTTP/DNS 和定时字段。
5. 巡检运行详情，突出成功、失败、慢响应。
6. 诊断页，突出故障类型和建议。
7. 告警中心，突出确认和恢复。
8. 报告管理和 Excel 文件。
9. 资产发现扫描结果。
10. 逻辑拓扑图。

## 注意事项

- 截图前建议先执行一次演示巡检，保证页面有数据。
- 告警演示可临时把阈值调为 1/1，截图后恢复默认 3/2。
- 资产发现只截授权小范围扫描结果，例如 `127.0.0.1`。
