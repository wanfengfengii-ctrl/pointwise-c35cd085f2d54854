# 导览换路事故记录

两次对照都用 `examples/day.json` 的开场布线。第一次保留 S→A 和 A→B，把通往听众端的出口从 A→T 改成 B→T。测试夹具让 B 实接后丢失回包，通过 `/live` 和 `/timeline` 对照当时的线路。改回开场线路后，重投 B 的旧动作，核对原实接序号和复盘。

第二次使用样例的整厅换路目标。在首个动作实际接线前暂停投递，再提交改回开场线路的请求。若仍待查，夹具投递一次滞留动作并续办改案。改案完成后再次投递同一动作，检查 A→B 返听和实接流水。

`python3 -B incident.py` 运行这两个窗口，各自使用临时库和现有 HTTP 入口。命令因业务断言失败时返回非零。`python3 -B check_project.py` 运行全套旧回归。`python3 -B demo.py` 从发布走到收班并核对普通换路。

## 根因与修复实测

- 只换 T 出口时出现双路：`control/dispatch.py` 的 `_prepare_next` 里有一段“开局仅一条新增边就直接安装”的捷径，绕过 `route_search` 对每个候选图的唯一送声校验，先接通 `B→T`，而 `A→T` 仍在、`A→B` 又把声送到 B，于是 T 同时听到 A 直送和经 B 转送。已删除该捷径，所有实接步统一取自最少端步搜索；该目标的合法绕行是 A 拆 `A→B`、B 接 `B→T`（此时 B 无入边，仍唯一）、A 再把出口 `A→T` 一次换成 `A→B`。
- 已实接旧步重投被误判：`endpoint/local_wiring.py` 原逻辑要求“当前实接等于该步后态”才返回原回执；改案把线路改走后该条件失效，原结局和序号变成 `rejected/STALE_WIRING`。现在只要 `wiring_commits` 已有该（场、原号、步）的实接记录，就无条件返回原 `applied` 结局和原 `sequence`，与后续改线无关，实接归属仍是旧原号。
- 迟到旧拆线仍改线：对从未实接（无提交记录）的旧令，单靠 `actual == command.expected` 无法识别其原单已被改案结清；改回开场后现状恰好等于旧令前态，迟到的 A 步便又拆掉 `A→B`。现在实接前先查 `orders`：原单已 `completed/rejected`（含 `SUPERSEDED`）时，对无回执旧步直接回 `rejected`（沿用原单 `reason`）且不写接线、不增序号；只有仍活跃（含 `suspended` 待结清）的原单才做前态一致校验。另在端点落库前用同一 `assess_paths` 复核候选图，非唯一/回授/无声一律不落线。
- 同号同参续办、复领与异参 `OPERATION_CONFLICT` 维持 README 约定；接口形状未改。

实测（仓库根目录，Python 3.11）：`python3 -B incident.py` 2 窗口全部 OK；`python3 -B check_project.py` 为 16 例全部 PASS（原 9 例回归保留并通过，另在 `tests/test_incident_fixes.py` 补 7 例：安全绕行计划、逐步唯一、两类失答窗口的回执/围栏、HTTP 续办、改案后收班封存、端点不安全提交兜底）；`python3 -B demo.py` 退出 0，五次差分时间线不变。


`.pointwise-runtime.json` 记录服务的运行入口。`start` 用平台分配的主机和端口启动，监听地址为 `127.0.0.1`，`readiness_path` 查询一个尚未开场的独立场次。`verify` 核对原回归及事故，`demo` 演示普通换路。使用 `POINTWISE_GUIDE_DB` 可指定启动时的数据库路径。
