# Phase 5.6 Refinement Loop Evidence（Agent 归档，验收证据）

- 项目：`experiment/AI_test2`
- 生成时间：见文件 mtime；数据源：project.json（schema v1 tolerant extra_fields）

## 训练轮次（按 validation series 归类）

- `9d310620` iter=None mode=restart series=— train_labels=0 val_rmse=4.12 train_rmse=5.94 epochs=50
- `f8d5fe67` iter=1 mode=resume series=f13d5bbd train_labels=19 val_rmse=3.3 train_rmse=3.43 epochs=25
  - resume_from: `9d310620`
- `e976e5dc` iter=2 mode=resume series=f13d5bbd train_labels=29 val_rmse=4.8 train_rmse=4.91 epochs=25
  - resume_from: `f8d5fe67`
- `18d1f638` iter=3 mode=restart series=f13d5bbd train_labels=29 val_rmse=3.19 train_rmse=3.16 epochs=50
- `b80fbd68` iter=4 mode=restart series=f13d5bbd train_labels=39 val_rmse=4.71 train_rmse=4.67 epochs=50

## 三类 delta（同 series 相邻两轮）

### f8d5fe67 → e976e5dc

- **精度**：validation RMSE 3.3 → 4.8 （+45.5%，worsened）
- 训练集 RMSE 3.43 → 4.91 （+43.1%）
- **工作量**：审核 remaining — → —；correction yield 0/0

### e976e5dc → 18d1f638

- **精度**：validation RMSE 4.8 → 3.19 （-33.5%，improved）
- 训练集 RMSE 4.91 → 3.16 （-35.6%）
- **覆盖**：prediction coverage 100.0% → 100.0% （informational only, not accuracy）
- **工作量**：审核 remaining — → —；correction yield 0/0

### 18d1f638 → b80fbd68

- **精度**：validation RMSE 3.19 → 4.71 （+47.6%，worsened）
- 训练集 RMSE 3.16 → 4.67 （+47.8%）
- **覆盖**：prediction coverage 100.0% → 100.0% （informational only, not accuracy）
- **工作量**：审核 remaining — → —；correction yield 0/0


## 判定（AC-9：同 series 上 ≥5% 改善才算达成）

- 基准轮 `f8d5fe67` val_rmse=3.3；最佳轮 `18d1f638` val_rmse=3.19（-3.3%）
- 最新轮 `b80fbd68` val_rmse=4.71（+42.7% vs 基准）
- **结论：未达成** —— 同 series 上的最佳改善在 ±5% 内（plateau）；≥5% 的改善证据缺失，需按 spec 处置或扩大实验。

## 复现性（训练确定性）

- `9d310620` snapshot sha256=2f8612d499e17048 size=94319571
- `f8d5fe67` snapshot sha256=b631d7270a33761f size=94319571
- `e976e5dc` snapshot sha256=4c24102d9f40a1a7 size=94319571
- `18d1f638` snapshot sha256=baa9a98f6624da17 size=94319571
- `b80fbd68` snapshot sha256=5784b6ab018d985b size=94319571

> 相同标签集与训练配置若出现相同 sha256，即证明本流水线的训练与评价是确定性的——delta 是可复现的真实效果，而非 run-to-run 噪声。

## 推理结果与激活

- `6b625037` model_train=`9d310620` coverage=None activated=否
- `0daad555` model_train=`9d310620` coverage=1.0 activated=否
- `cee507bc` model_train=`e976e5dc` coverage=1.0 activated=否
- `19c2223c` model_train=`e976e5dc` coverage=1.0 activated=否
- `cffbed09` model_train=`18d1f638` coverage=1.0 activated=否
- `aa1ade22` model_train=`b80fbd68` coverage=1.0 activated=否

## 激活历史

