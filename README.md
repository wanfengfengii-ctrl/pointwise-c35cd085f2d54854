# 海榆展馆双语导览控台

机务员按当班配线表发布线路，讲解员绑定起点开场，值班员在两个讲解厅间在线换路。下一班按现场实接顺序核对线路变化及原操作归属。服务记录离散接线状态，运行只需 Python 3.11 标准库和 SQLite。

## 运行

在项目根目录运行正常回归及演示。

```sh
python3 -B check_project.py
python3 -B demo.py
```

`check_project.py` 由运行平台提供，执行 `tests` 包内完整的 `test_*.py` 套件。单独检出源码时可运行 `python3 -B -m unittest discover -s tests -t .`。演示以临时库运行真实 HTTP 服务，从 `examples/day.json` 发布、开场、预览、换路并封存，逐笔核验实接后输出实测记录。

手动启动时使用 `python3 -B -m control.http_api --db guide.sqlite3 --port 8765`。服务监听 `127.0.0.1`。首次初始化建表，重开保留实际接线、发布、原单、端点结局和收班记录。样例不会随初始化自动写入。

## JSON HTTP

POST 接收 JSON 对象。每个请求需提供 `session`，GET 将字段放在查询字符串。场次、端口、接线端和操作使用去掉首尾空白的非空名字。边采用 `[起点, 终点]`，允许线路采用 `[起点, 终点, 所属接线端]`。端口和接线端分别命名。同一条边只有一个归属，边集比较忽略顺序和重复边。

| 方法与路径 | 请求字段（另含 `session`） | 成功结果 |
| --- | --- | --- |
| `POST /publish` | `layout` 含 `ports`、`start`、`listener`、`allowed`、`initial` | `published`，线路 `reference` 及 `path` |
| `POST /open` | `reference`、`input` | `open`，当班绑定及实际边集和听众路径 |
| `POST /preview` | `target` | `reachable`，目标听众路径及逐端 `steps` 摘要 |
| `POST /change` | `operation`、`target`、可选 `replaces` | `pending` 或 `completed`，原号、完整目标、终态边集及原单实接 |
| `GET /session` | 无 | `state` 为 `unopened`、`open` 或 `closed`，已开过的场次包含发布及输入绑定 |
| `GET /live` | 无 | `edges`、路径判定 `assessment` 以及唯一时的有序 `path` |
| `GET /timeline` | 无 | `initial` 及按实接顺序的 `commits`，每笔含差分与提交后的图 |
| `GET /orders` | 无 | 按受理顺序列示本场换路原单 |
| `GET /order` | `operation` | 原单状态、目标、终态边集和归属该原单的实接 |
| `POST /close` | `close_id` | `closed`，封存的 `live`、`orders` 和 `timeline` |
| `GET /report` | `close_id` | 按原收班号复领封存结果 |

发布引用绑定不可变的线路定义。同一场次可预先发布多套线路，开场将本场绑定到指定发布。开场请求的 `input` 必须是发布起点。同参重投已开场的开场请求时复用绑定，并返回现场当前线路。初始装线作为场次开场基准。

系统检查全图的有向环，静默支路和听众端出线都参与检查。无环时计数从起点到听众端的路径，计数在两条截断。起点就是听众端时零跳路径计作一路。`assessment` 可为 `unique`、`silent`、`duplicate` 或 `feedback`。返听端空闲时可以没有出线。规划遍历允许图中每个端点可一次安装的出线集合。每步只改一端，整个图须唯一送声且无环。搜索返回最少的端点提交步数，按接线端及边的固定顺序探索。规模随允许边集合增长，样例使用有限的展厅配线表。

预览读取一个一致的现场快照。换路受理时从实接边集重新核对。每场一次推进一个操作。失答时 `POST /change` 可返回 HTTP 202，重投原号和原参数可续办，查询原号只读。显式改案将待查原号填入 `replaces`，旧案已有实接仍归旧号，旧步骤结清后才能按实接前态推进新案。结清的旧案可查询，原号状态显示 `rejected` 和 `SUPERSEDED`。同号更改完整目标或所替代的旧号返回 `OPERATION_CONFLICT`。实接的正整数 `sequence` 从每个场次的 1 开始，只有实接发生变化时才增加。

拒绝结果包含 `status: rejected` 与 `reason`。请求格式错误返回 HTTP 400。未知引用、原操作或收班号返回 404。输入或线路不合法以及找不到逐端合法序列返回 422，可见 `INPUT_MISMATCH`、`FEEDBACK_LOOP`、`NO_LIVE_PATH`、`DUPLICATE_LIVE_PATH` 和 `UNREACHABLE_TARGET` 等原因。状态冲突返回 409，包括活跃操作期间无替代关系的新单、待查期间收班、已收场时提交新单。查询已受理原单用 HTTP 200 返回其原状态。收班同号可复领。

## 当班样例

配线表开场是 `S→A→T`，另有 `A→B` 作返听。B 厅接班的目标是 `S→B→T`，返听改为 `B→A`。正常样例依次拆 `A→B`、接 `B→T`、在 S 端把出线从 A 换到 B、拆 `A→T`，最后接 `B→A`。收班记录保留五次实际差分和各步当时的线路。接口回归还覆盖错配开场、全图反馈、静态合法但无法逐端到达的双端交叉线路、实接前后两个失答窗口、原号复领及落盘重开。
