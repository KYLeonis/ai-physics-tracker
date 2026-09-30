# Independent Review — Publication P2.2

- Date：2026-09-30；branch `feat/p2.2-angular-analysis`，base `ad46b31`。
- Scope：AngularSeries、直接 SG9/3、各 extrema profile、分段 crossing/period/tail、identity、P2.1 adapter 与 synthetic/frozen E1 回归。
- Reviewer：fresh-context 只读 `p2_2_review`；首轮定向19 tests及 frozen evidence verifier通过。首轮 Verdict **request-changes**。

| ID | Finding | Fix / status |
| --- | --- | --- |
| F1 (P1) | 连续零平台被当 crossing，重复[-1,-1,0,0,1,1,0,0]可报77周期/25 tail周期 | student：连续 raw/centered 零平台切段；孤立零点需两侧异号，触零返回/段首零点不计。保留原窗口mean，不压缩时域；legacy unchanged。Closed，复审确认 |
| F2 (P2) | derivative sources 顺序与冻结student profile不同 | 改为 policy-student-v1,metrics；明确断言与profile一致。Closed，复审确认 |

## Self-review / Verification

- Diagnostic extrema config 补齐 NumPy/SciPy 实际版本进入摘要。
- 修复前全量1206 passed/9 subtests；修复后定向20 passed，全量1207 passed/9 subtests。P011/P014 SG1e−8、P011213有序extrema精确一致、tail crossing/period1e−8及q1e−7均通过。expected未修改。
- 原科研 information/phase/energy/tail 四入口 SHA与source-map一致，只读未执行。
- 复审 **approve**，F1/F2 Closed，无开放 blocking finding；独立探针零平台0 crossings/0 periods，tail insufficient_data。无GUI增量，真人验收留P2.3。
