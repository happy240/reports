# 喜越农场数据目录

生成时间：2026-10-22T23:15:51

展示名称：**喜越农场**。库内常见写法：`喜越农业` / XYNY / `xiyue`。`rockai.zhny_farm.id = 8`。

## 报表数据源（当前）

| 优先级 | 库 | 用途 |
|--------|-----|------|
| **主** | **db3** `agromind.farming_irrigation_record`（`farm='xiyue'`） | 水肥/尾水手填：日期 × 棚 × 电磁阀 × 进/尾水 pH·EC |
| 辅 | db1 `monitor` | 同棚 environment 温湿度；A3/B3 等自动 `tail_water_irrigation_summary` |
| — | db2 `rockai` | 喜越无传感器时序，报表不接 |

address 样例：`弥勒农场-A2-5` → 棚 `A2`、电磁阀 `5`。

## 文件说明

| 文件 | 用途 |
|---|---|
| `index.json` | 开发常用摘要：表、行数、设备列表、farm_id、join 提示 |
| `catalog.json` | 完整目录：含字段、索引、设备明细、空表排查结果 |
| `README.md` | 本说明 |

## monitor（db1）

- 匹配：`sensor_device.farm` ∈ `['喜越农业', '太仓总部，喜越农业']`
- 设备数：21（按类型：{'weather': 1, 'environment': 17, 'tail_water': 3}）

| 表 | 行数 | 角色 | Join |
|---|---:|---|---|
| `sensor_device` | 21 | 设备主数据 | `farm LIKE '%喜越%'` |
| `device_data` | 95,412 | 传感器时序原始数据 | `device_id IN (喜越 sensor_device.id)` |
| `tail_water_irrigation_summary` | 443 | 尾水单次灌溉汇总 | `device_id / device_sn 关联喜越尾水设备` |

以下表已按 farm 文本排查，**无喜越数据**：

`assistant_report`, `crop_phenotype_records`, `farm_work_records`, `farming_record`, `irrigation_data`, `phenotyping_data`, `plant_protection_data`, `plant_protection_records`, `substrate_humidity_records`, `tailing_data`

### 设备清单

| id | sn | type | name | region | farm | device_data 行数 |
|---:|---|---|---|---|---|---:|
| 32 | 40419014 | weather | 室外气象站 | 室外 | 太仓总部，喜越农业 | 32,294 |
| 39 | 24314963 | environment | A1 | A1 | 喜越农业 | 6,660 |
| 40 | 24315009 | environment | A2 | A2 | 喜越农业 | 3,147 |
| 41 | 24315004 | environment | B1 | B1 | 喜越农业 | 5,550 |
| 42 | 24314968 | environment | B2 | B2 | 喜越农业 | 4,919 |
| 43 | 24315001 | environment | B4 | B4 | 喜越农业 | 5,529 |
| 44 | 24315002 | environment | B5 | B5 | 喜越农业 | 5,410 |
| 45 | 24314986 | environment | B6 | B6 | 喜越农业 | 3,809 |
| 46 | 24314965 | environment | B7 | B7 | 喜越农业 | 3,799 |
| 47 | 24314980 | environment | B8 | B8 | 喜越农业 | 3,569 |
| 48 | 24314982 | environment | B9 | B9 | 喜越农业 | 3,698 |
| 49 | 24314978 | environment | C1 | C1 | 喜越农业 | 2 |
| 50 | 24314975 | environment | C2 | C2 | 喜越农业 | 1 |
| 51 | 24314997 | environment | C3 | C3 | 喜越农业 | 1 |
| 52 | 24315006 | environment | C4 | C4 | 喜越农业 | 6,265 |
| 53 | 2637050603 | environment | A3室内气象站 | A3 | 喜越农业 | 3,043 |
| 54 | 2637050602 | environment | B3室内气象站 | B3 | 喜越农业 | 3,046 |
| 55 | 2637050601 | environment | B7室内气象站 | B7 | 喜越农业 | 3,047 |
| 56 | 2636040101 | tail_water | A3尾水设备 | A3 | 喜越农业 | 449 |
| 57 | 2636040102 | tail_water | B3尾水设备 | B3 | 喜越农业 | 475 |
| 58 | 2636040105 | tail_water | A3尾水设备2 | A3 | 喜越农业 | 699 |

## rockai（db2）

- `farm_id=8`，`farm_short_name=XYNY`，`farm_name=喜越农业`
- 分区 area_ids：[114, 115, 116]

| 表 | 行数 | 角色 |
|---|---:|---|
| `zhny_task` | 123 | 任务 |
| `zhny_task_push` | 30 | 任务推送 |
| `zhny_app_login_info` | 8 | App 登录记录 |
| `zhny_ai_history` | 7 | AI 对话/历史 |
| `zhny_area` | 3 | 种植分区 |
| `zhny_user` | 3 | 农场用户账号 |
| `zhny_program_area` | 1 | 灌溉/种植程序区 |
| `zhny_task_rule_config` | 1 | 任务规则配置 |

### 分区

- id=114 C区 作物=草莓 面积=32.68
- id=115 B区 作物=草莓 面积=60.82
- id=116 A区 作物=草莓 面积=19.87

### 用户

- id=40 `XYNYguangai` 灌溉主管
- id=41 `XYNYzhibao` 植保主管
- id=42 `XYNYnongshi` 农事主管

### 当前为空（开发时勿假设有数据）

`zhny_device_config`, `zhny_env_sensor_data`, `zhny_weather_sensor_data`, `zhny_farm_record`, `zhny_irrigation_plan`, `cloud_farm_records`, `cloud_daily_reports`, `cloud_weekly_reports`

## 跨库现状

- 喜越传感器时序在 monitor.device_data，rockai 无 farm_id=8 的环境/气象数据
- rockai.zhny_device_config 无喜越设备，两端设备主数据未打通
- monitor 农事/表型/灌溉日表无喜越；rockai 农事记录/灌溉计划亦为空，仅有任务体系

## 推荐查询

**monitor 设备列表**

```sql
SELECT * FROM sensor_device WHERE farm LIKE '%喜越%'
```

**monitor 时序**

```sql
SELECT d.* FROM device_data d JOIN sensor_device s ON s.id=d.device_id WHERE s.farm LIKE '%喜越%'
```

**monitor 尾水汇总**

```sql
SELECT t.* FROM tail_water_irrigation_summary t JOIN sensor_device s ON s.id=t.device_id WHERE s.farm LIKE '%喜越%'
```

**rockai 农场与分区**

```sql
SELECT f.*, a.* FROM zhny_farm f LEFT JOIN zhny_area a ON a.farm_id=f.id WHERE f.id=8
```

**rockai 任务**

```sql
SELECT * FROM zhny_task WHERE farm_id=8
```
