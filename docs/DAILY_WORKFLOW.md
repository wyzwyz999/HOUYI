# HOUYI 每日标准流程（v2.0）

> 适用版本：`v2-resilient-20261025` / tag `v2.0`
> 核心变化：任一环失败不再中断；默认 reviewed 优先、失败自动降级 TrEMBL；每株产物带 `run_summary.json`。

---

## 0. 开机自检（3 条）

1. AutoDL 控制台 → 实例 → **开机**，等状态变「运行中」。
2. 进 JupyterLab → 打开终端（或本地 `ssh -p <端口> root@connect.westd.seetacloud.com`）。
   ⚠️ 每次开机**端口可能变、密码可能重置**，以控制台「登录指令」为准。
3. 三条命令确认环境：

```bash
cd /root/autodl-tmp/HOUYI_git
git status -sb            # 看分支与未提交改动
nvidia-smi                # GPU 是否可见、显存是否是空的
df -h /root/autodl-tmp    # 数据盘剩余空间，建议 > 20G
```

---

## 1. 跑一株菌（只改菌名）

```bash
cd /root/autodl-tmp/HOUYI_git && bash scripts/run_species.sh "菌名"
```

后台运行（推荐，断开 SSH 也不中断）：

```bash
cd /root/autodl-tmp/HOUYI_git
nohup bash scripts/run_species.sh "菌名" > "logs/$(date +%Y%m%d_%H%M%S).log" 2>&1 &
tail -f logs/*.log
```

**耗时参考**：环1 1–2 分钟 → 环2/3 30–60 分钟 → 环7/8 20–40 分钟，整株 **1.5–3 小时**。

**菌名必须用 UniProt 的 `organism_name`（拉丁种名）**，不要写中文、缩写、血清型：

| ❌ 错 | ✅ 对 |
|---|---|
| Adherent-invasive E. coli | Escherichia coli |
| S. Typhimurium | Salmonella typhimurium |
| Shiga toxin-producing E. coli | Escherichia coli |
| Prevotella copri | Segatella copri |

---

## 2. 中途看进度（另开一个终端）

```bash
tail -f logs/xxx.log
grep -E "环 [0-9]+：|运行总结" logs/xxx.log | tail -5
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv
```

- `Ctrl+C` 只停 `tail`，**不会杀掉**后台任务。
- 真要中断：`pkill -f "pipeline.py.*菌名"`（慎用）。

---

## 3. 跑完：一条命令出摘要 + 打包

```bash
bash scripts/pack_result.sh "菌名"
```

输出示例：

```
=== 质量摘要: Nocardia brasiliensis (nocardia_brasiliensis) ===
overall_status : COMPLETED
blocked/failed : 无
fiber_tier     : exploratory | counts: {'exploratory': 8}
nanosyringes   : 3 | complete: 3 | complete_strict: 0
ring7 #1       : AUTO_A0ACH2ZSV3 | phospholipase C | tier: exploratory

=== 打包 ===
原始大小: 1.1G   压缩包: 305M   条目数: 471
压缩包路径: /root/autodl-tmp/nocardia_brasiliensis_results_20261025.tar.gz
```

### 结果判定

| overall_status | 含义 | 怎么用 |
|---|---|---|
| `COMPLETED` + `complete_strict > 0` | 全跑完，尾纤维来自 curated/reviewed | **高置信，可直接用** |
| `COMPLETED` + `complete_strict = 0` | 全跑完，但尾纤维是降级候选 | **探索性草案**，看 ring7 #1 是否合理 |
| `PARTIAL` | 有环节失败/被跳过 | 看 `blocked_or_failed`，缺的部分用 `--start` 补跑 |
| `FAILED` | 没有任何交付物（多为菌名不合法） | 改名重跑 |

> 记住：**跑通 ≠ 可信**。`exploratory` / `fallback` 是 UniProt TrEMBL 自动注释捞出来的，
> 需要人工看一眼 `ring7_fiber_targets.json` 的 #1 是不是真表面受体（别是 Enolase/GroEL 这类管家酶）。

---

## 4. 下载结果

- 控制台 → **文件存储** → `/root/autodl-tmp` → 下载 `*.tar.gz`
- 或 JupyterLab 文件树里右键该文件 → **Download**

---

## 5. 一天跑多株（批量）

新建 `species.txt`（每行一个，`#` 是注释）：

```
Mycobacterium simiae
Nocardia brasiliensis
Desulfovibrio piger

# 别名改写：左边只做记录，右边才是真正传给管线的标准名
Shiga toxin-producing Escherichia coli => Escherichia coli
Brucella spp. => Brucella melitensis
```

运行：

```bash
cd /root/autodl-tmp/HOUYI_git
nohup bash scripts/batch_species.sh species.txt > batch.out 2>&1 &
tail -f batch.out
```

结果：`logs/batch_<时间>/ok.txt`、`fail.txt`、`partial.txt`，每株独立日志。

---

## 6. 断点续跑（某环失败，不想从头）

```bash
bash scripts/run_species.sh "菌名" --start 8 --stop 10
```

⚠️ `--start > 1` 时，**菌名必须与上次一致**（state 里有记录），否则会拒绝执行。

---

## 7. 每天收尾（2 分钟）

```bash
# 谁占空间
du -sh results/by_organism/* | sort -h | tail -10

# 已打包的压缩包
ls -lh /root/autodl-tmp/*.tar.gz | tail

# 磁盘
df -h /root/autodl-tmp
```

- **先打包、确认下载完，再删** `results/by_organism/<菌>/` 里的大中间文件（`tail_fiber_rbd/`、`af2_validation/`）。
- `/root/autodl-tmp` 是数据盘，**关机不丢**；`/root/` 下的其他位置属于系统盘，换实例会没。
- `results/` 已被 `.gitignore` 排除，不会被提交。

---

## 8. 代码更新（有新版推上来时）

```bash
cd /root/autodl-tmp/HOUYI_git
git stash push -u -m "before-pull"     # 先保住本地未提交改动
git pull --rebase origin main          # 或指定分支名
git stash pop                          # 有冲突就手工解
```

**不要用 `git push --force` / `git reset --hard`**，那是唯一会把别人工作覆盖掉的操作。

---

## 9. 常见报错对照表

| 现象 | 原因 | 处理 |
|---|---|---|
| `完全查不到记录（reviewed 与 TrEMBL 都是 0 条）` | 菌名不合法 | 换标准拉丁名 |
| `reviewed 为 0 条` 且流程中断 | 在严格模式 | 去掉 `HOUYI_STRICT_PIPELINE=1`（默认会自动降级） |
| `ColabFold MSA阶段最终失败` | 网络/超时 | v2 起只跳过 AF2 验证，环5–10 继续 |
| 环7 无候选 | 老版本 | v2 起四级降级，不会空 |
| `CUDA out of memory` | 骨架数太多/显存不够 | 减小 `--num-designs`，或换大显存实例 |
| 磁盘满 | 中间文件堆积 | 打包后清理 |
| `git pull/push` TLS 报错 | 未开加速 | `source /etc/network_turbo` |
| `python: command not found` | 没 source 环境 | 一律用 `bash scripts/run_species.sh`，它内部会 source |

---

## 10. 三条最常用命令（贴在便签上）

```bash
cd /root/autodl-tmp/HOUYI_git && bash scripts/run_species.sh "菌名"     # 跑
bash scripts/pack_result.sh "菌名"                                      # 摘要+打包
bash scripts/run_species.sh "菌名" --start 8 --stop 10                  # 断点续跑
```
