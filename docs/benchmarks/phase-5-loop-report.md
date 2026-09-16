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


## 推理结果与激活

- `6b625037` model_train=`9d310620` coverage=None activated=否
- `0daad555` model_train=`9d310620` coverage=1.0 activated=否
- `cee507bc` model_train=`e976e5dc` coverage=1.0 activated=否
- `19c2223c` model_train=`e976e5dc` coverage=1.0 activated=否
- `cffbed09` model_train=`18d1f638` coverage=1.0 activated=否

## 激活历史

