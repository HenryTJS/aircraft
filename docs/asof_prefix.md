# L1-13 与 main-016 as-of 前缀切片

## 目的

把“回放位置”与“在线状态”分开。看板上的 `cycle / N_f` 是事后回放；`/api/asof` 只回答查询时刻之前的累计状态，不返回全寿命 `t85`。

当前覆盖 L1-13（AE hits + PZT）和 main-016（AE 窗能量/累积对数能量），用来证明协议与泄漏边界，不宣称已经完成全量在线监测。

## 数据来源

`tools/build_prefix.py` 从以下 raw 派生缓存生成 `prefix/L1-13.npz`：

- `D:/shm/l1/results/_l1cyc_L1-13.npz`：`t_epoch`、`cycle`、`n`、`frame_s`
- `D:/shm/l1/results/_l1ae_frames_L1-13.npz`：逐帧 hits
- `D:/shm/l1/results/pzt_crosslab.csv`：L1-13 的 `cycle`、`D`、`tof_us`

输出字段：

- `t_s`、`cycle`、`frame_hits`、`cum_hits`、`hit_rate_h`
- `pzt_cycle`、`pzt_d`、`pzt_tof_drift`
- 不写 `t85`，不写 `n_f`

当前实测：`frames=360`，`first_cycle=675.6`，`last_cycle=243000.0`，`pzt_states=47`。

重新生成：

```bash
conda run --no-capture-output -n xjtushm python tools/build_prefix.py
```

## main-016

`tools/build_prefix_main.py` 从 `E:/main/016/016声发射.csv` 的 `SpectralEnergy` 列生成 `prefix/main-016.npz`：

- `t_s = index * 0.1594`，与看板包 `window_s=0.1594` 一致
- `cycle = t_s * 5.0`，主样本是 5 Hz 正弦
- `frame_energy`、`cum_energy`、`ce_log = cumsum(log1p(frame_energy))`
- 不写全寿命总能量、不写 `t85`、不写 `n_f`

31,442 个窗；`last_s=5011.7`，`last_cycle=25058.5`。重新生成：

```bash
conda run --no-capture-output -n xjtushm python tools/build_prefix_main.py --gid 016
```

API 别名：`gid=016` 与 `gid=main-016` 等价，响应中的 `gid` 为 `main-016`，`dataset` 为 `main`。`state` 返回 `frame_energy`、`cum_energy`、`ce_log`，不返回 `t85`。这组量是记录进度，不是损伤度，也不是 RUL。

## API

`GET /api/asof?gid=L1-13&cycle=100000`

`GET /api/asof?gid=016&cycle=10000` 返回 main-016 的前缀状态。

也支持 `at_s`，两者都给时 `cycle` 优先。返回：

```json
{
  "status": "ok",
  "gid": "L1-13",
  "asof": {"elapsed_s": 2702.5, "elapsed_h": 0.75, "cycle": 99992.58},
  "state": {
    "frame_index": 147,
    "cycle": 99992.58,
    "cum_hits": 2834679,
    "frame_hits": 19121,
    "hit_rate_h": 114726.0
  },
  "pzt": {"cycle": 98800.0, "age_cycles": 1192.58, "D": 0.11637, "tof_drift_us": -4.75},
  "boundary": {
    "axis": "cycle",
    "t85_available": false,
    "contains_future": false,
    "reason": "prefix only; t85 requires the completed test and is not an online value"
  }
}
```

未知 gid 404，prefix 缺失 503，查询早于首帧 400。

## 不泄漏的检查

`web/tests/test_asof.py`：

- `test_returns_prefix_only`：响应没有 `t85_pct`/`n_f`，`contains_future=false`。
- `test_monotonic_prefix`：`cycle` 与 `cum_hits` 单调。
- `test_future_invariance`：把 prefix 截到 100000 再查同一 cycle，`state`、`pzt`、`asof` 与完整 prefix 完全一致。
- `test_before_first_frame`、`test_unknown_gid`。
- `test_main_prefix_only`、`test_main_future_invariance`：main-016 只返回前缀能量/CElog，截断未来后同一 cycle 的状态不变。

7/7 通过。浏览器端从 L1-13 看板点“当前时刻状态”，显示当前 cycle、累计 hits、hit rate、PZT 最近状态和边界说明。

## 边界

- `PZT` 是最近一个不晚于查询 cycle 的状态，不是插值；`age_cycles` 是它与当前 cycle 的差。
- `t85` 需要整场试验，在线不可用；这里明确拒给。
- 前缀最后一帧可能略早于看板当前帧，因为看板数据包与 `_l1cyc` 缓存来自不同导出批次；不是用了未来数据。
- 当前只支持 L1-13 与 main-016；其他 L1 组、main 其余组、L2、F-MOC 没有在线前缀。
- main-016 的 `cycle` 由 0.1594 s 窗与 5 Hz 载荷换算，和看板回放口径一致；它仍是记录进度，不是损伤度或 RUL。
- main-016 的前端入口尚未接到主样本看板；目前通过 API 查询。

## 验证

```bash
node --check web/static/assistant.js
node --check dashboard/assets/dashboard.js
conda run --no-capture-output -n xjtushm python -m unittest web.tests.test_asof -v
```

浏览器 E2E：加载 `L1-13`，打开证据助手，点“当前时刻状态”；实测返回约 `230,388 cycle`、`9,247,312` 累计 hits、PZT `D=0.036`、`ΔTOF=2.00 µs`，且 `t85_available=false`。
