# Publication P5.1 Independent Review

- 日期：2026-10-02；reviewer：gpt-6-luna/max；主实现方：root。
- 范围：`e166f0a..9f5cff7`工作流投影/状态头/模型入口/取消恢复；R2核对`4238f8a`的F1修复。
- 最终Verdict：**Approve，F1 Closed，无开放finding**。本记录不代替最终Human Review或学生pilot。

## R1

Request Changes：F1/P2——最新合法nonconverged拟合未计入current，也没有明确限制；与成功Kinematics并存时可能错误呈现latest。

独立定向91 passed；diff check通过。Review只读，P5.2切分支/在途文件不纳入首轮范围。

## R2

`4238f8a`将nonconverged计为current-but-partial，failed/cancelled也给显式状态原因。真实max_nfev=1 fit回归覆盖alone与加成功Kinematics两个组合。

Reviewer独立`tests/test_publication_workflow.py`：3 passed；F1 Closed，Approve。最终HR仍待用户，未声明学生实测或Windows真机门禁通过。

## P5 阶段HR与最终CI确认（2026-10-02）

用户明确整体HR通过并授权收尾；独立审查既有verdict/finding不变。最终源码98bfd25双平台CI通过（macOS1382/Windows1380 passed，各1既有strict xfailed）；冻结15/48/2通过。收尾仅文档与集成，不修改已审代码或科学证据。外部学生pilot/Windows副本重开保持not_run，发行前待补，不把用户HR当作该实测。
