# ADR 0018: 角运动分析以tip与fixed pivot为主，辅助点不作硬门槛

## Status

Accepted (2026-09-30)，用户本轮明确纠正分析用途。

## Context

θ公式始终由tip−calibrated fixed pivot与true vertical决定；原student-default-v1却把body pair/tracked pivot的完整性与长度QC作为统一角运动门槛。真实HR中已有连续可信tip仍无法生成ω/相图，要求用户补辅助点偏离用途。

## Decision

新默认student-default-v2：tip source validity、正半径、既有radius tolerance和人工排除决定角运动mask。辅助role缺失/异常独立记录auxiliary_qc_reasons，仅影响自身诊断。body reference取有效body pair，无需tip或tracked pivot同时存在。θ/ω/phase/period/reference energy共用tip mask；SG9/3、时间/缺口规则、能量公式与单位不变。

训练/联合推理仍使用四role数据体系；分析修复仅重标tip。保留v1/legacy冻结文件与历史golden，新增版本/hash/core version使旧结果stale，重新计算生成新immutable结果。

## Consequences

辅助跟踪质量不再阻断角运动图。tip缺测、无效likelihood、半径异常或短连续段仍不生成导数；本决策不会自动采用低置信度raw预测。历史结果可查看但不能标为当前结果。未来拟合/IC必须消费新默认tip mask，不沿用旧完整四点门槛。
