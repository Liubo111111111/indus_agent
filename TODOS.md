# TODOS

## TODO 1: 固化正式 taxonomy contract
- What: 把 11 类行业定义补成正式 `taxonomy contract`，补全 inclusion、exclusion、典型岗位、易混边界和 tie-break 规则。
- Why: 当前 [业务知识库.md](C:\Users\ASUS\Desktop\indus_agent\业务知识库.md) 只有自然语言定义，没有足够硬的工程边界，长期会造成 prompt 漂移和跨节点不一致。
- Pros: 分类更稳定，回归测试更清晰，静态画像/动态画像/最终裁决对标签的理解更一致。
- Cons: 需要额外业务梳理和样本复盘，会拖慢短期 prompt 迭代速度。
- Context: 在 `/plan-eng-review` 中已明确选择先开做，再边开发边补 taxonomy，因此这项工作被显式后延，但不能依赖口头记忆。
- Depends on / blocked by: 依赖 V1 跑起来后的 seed replay 和上线后人工标注样本，最好结合真实混淆案例推进。

## TODO 2: 增加 signal_quality_gate 节点
- What: 在 LangGraph 中增加独立 `signal_quality_gate` 节点，单独判断招聘信号是否足够可信，是否允许动态画像主导分类。
- Why: 当前 V1 直接把近 90 天招聘数据视为可信输入，没有单独过滤中介代招、模板 JD、重复上架、泛岗位名噪音。
- Pros: 能降低噪音信号主导分类的概率，减少错误高置信输出。
- Cons: 会增加一个图节点、一套规则或阈值逻辑，以及额外的测试样本和维护成本。
- Context: 在 `/plan-eng-review` 中已明确选择 V1 暂不做独立 gate，这项风险被后延处理，但后续不能遗忘。
- Depends on / blocked by: 依赖 seed replay 和上线后人工标注样本，最好基于真实误判案例来确定 gate 规则。

## TODO 3: 增加 manual override + rollback safety layer
- What: 为正式输出增加人工 override 和显式 rollback 安全层，支持快速止损和手动覆盖错误分类结果。
- Why: 当前 V1 选择直接替换正式输入，不走 shadow publish，一旦 taxonomy、prompt 或模型行为漂移，定价结果会直接受影响。
- Pros: 能明显降低生产事故 blast radius，出现误判时有可操作的回退路径。
- Cons: 会增加一层运营/数据治理逻辑，以及更多测试和审计要求。
- Context: 在 `/plan-eng-review` 中已明确接受直接正式发布，因此这项安全机制被明确后延，必须以 TODO 形式保留。
- Depends on / blocked by: 依赖正式输出表、审计元数据和低置信分流先落地，之后才能加 override/rollback 控制。
