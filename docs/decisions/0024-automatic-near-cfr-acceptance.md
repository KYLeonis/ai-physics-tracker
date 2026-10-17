# ADR-0024 — 自动采用合格的近似时序

## Status

Accepted for implementation，2026-10-17。用户明确要求取消Review timing与单独点击Yes。部分替代ADR-0007 Decision 4 / 5的人工接受要求；其余探测、预算、身份与时间语义不变。

## Context

Near-CFR已由程序检测并按实际Timeline计算误差上界。用户不希望普通实验者再判断并接受同一报告；打开或重开视频后应自动完成原Yes处理。P6.3.1的HR已通过，该需求是之后的独立改动。

## Decision

- 保留后台探测。CFR沿用原权限；Near-CFR在原误差预算、帧数及实际Timeline守卫通过后，自动调用现有接受路径，不弹窗、不显示Review timing / Use approximate timing按钮。同步打开、异步检测、重开及切视频使用同一策略。
- 自动接受只替代原本可点击Yes的人工动作；unknown、探测失败、取消、媒体不匹配、超预算与真正VFR仍保留具体原因及适用的Retry / Cancel操作，不编造FPS或时间戳。
- 自动接受在每次媒体会话重新检测后执行，不持久化跳过检测的权限。近似仍标为近似，显示Timeline FPS及两项误差。新观测 / 派生来源记录`timing_method=near_cfr_auto_accepted_v1`；旧`near_cfr_user_accepted_v1`保持原样且可读。
- `accept_approximate_timing(..., automatic=True)`用于GUI自动路径；默认参数保留旧显式调用来源，避免将既有人工参考或脚本的历史接受方式改写。无schema迁移、新依赖或原始观测 / 既有Timeline更改。

## Consequences

普通Near-CFR视频检测完成即可标注和分析；用户无需替程序作时序判断。误差上界仍不代表速度 / 加速度精度保证。新旧来源可区分，取消、换文件、保存忙和迟到交付守卫继续测试；新交互独立HR。
