# GAIA 测试缺陷与 open-managed-agents 实现对比分析

> 分析时间:2026-07-18  
> 目的:对比 GAIA 测试中发现的系统缺陷,检查 `open-managed-agents/` 是否已有对应实现,为 OMA 平台改进提供参考

---

## 一、缺陷清单与实现状态总览

| 缺陷编号 | 缺陷描述 | 严重度 | open-managed-agents 实现 | 状态 |
|---------|---------|-------|------------------------|------|
| **P0** | Session 终止失败(SSE 事件丢失) | 🔴 高 | ✅ 已实现 | **可参考** |
| **P1-a** | 工具调用死循环 | 🟡 中 | ✅ 已实现 | **可参考** |
| **P1-b** | 多跳查询能力不足 | 🟡 中 | ⚠️ 部分实现 | **需增强** |
| **P1-c** | 答案提取不完整 | 🟡 中 | ❌ 未实现 | **需新增** |
| **P2** | 冷门来源访问失败 | 🟢 低 | ⚠️ 部分实现 | **可优化** |

---

## 二、详细分析

### 🔴 P0:Session 终止失败(SSE 事件丢失)

**GAIA 测试现象**:
- 100% 的题目超时(即使 agent 已找到答案)
- Runner 等待 `session.status_idle` 事件,但 SSE 流未正确传递
- 导致所有题目浪费 120s 等待时间

**open-managed-agents 实现**:

✅ **已实现** - 位于 `apps/agent/src/runtime/session-do.ts`

```typescript
// Line 1050-1056
forceIdle: () => {
  // Status auto-derives to "idle" once recoverAgentTurn returns
  // and cf_agents_runs is empty. Just emit the trajectory event.
  const idleEvent: SessionEvent = { type: "session.status_idle" };
  history.append(idleEvent);
  this.broadcastEvent(idleEvent);
},
```

**关键实现点**:
1. **明确的 idle 事件发射**:在 turn 结束后主动发射 `session.status_idle`
2. **事件广播机制**:`this.broadcastEvent(idleEvent)` 确保事件推送到所有 SSE 订阅者
3. **历史持久化**:`history.append(idleEvent)` 保证事件不会丢失
4. **状态自动推导**:注释说明 status 会在 `recoverAgentTurn` 返回后自动推导为 idle

**参考建议**:
- 检查 OMA 的 `oma-platform/harness/oma_adapter/emit.py` 是否正确映射 `session.status_idle` 事件
- 确认 SSE 流的 `broadcastEvent` 机制是否正常工作
- 验证事件是否在 `history.append` 后被正确序列化

**相关文件**:
- `open-managed-agents/apps/agent/src/runtime/session-do.ts:1050-1056`
- `open-managed-agents/apps/agent/src/runtime/session-do.ts:1834-1837` (interrupt 后的 idle 事件)

---

### 🟡 P1-a:工具调用死循环

**GAIA 测试现象**:
- Agent 在工具调用失败后无限重试相同调用
- 典型案例:Q6 做了 10 次工具调用仍未提取出答案
- 浪费 token 且无法产生答案

**open-managed-agents 实现**:

✅ **已实现** - 位于 `apps/agent/src/harness/platform-guidance.ts`

```typescript
// Line 14-15
export const loopStopGuidance =
  "If the same tool call fails three times in a row with substantively " +
  "the same error, stop retrying. Report (a) what you were trying to do, " +
  "(b) the exact error, and (c) what you would need to make progress " +
  "(a missing credential, a corrected input, an upstream service to recover), " +
  "then end the turn instead of looping.";
```

**关键实现点**:
1. **System Prompt 注入**:通过 `platformGuidance` 自动注入到每个 agent 的 system prompt
2. **三次失败规则**:明确告诉 agent 同一工具连续失败 3 次后停止
3. **结构化失败报告**:要求 agent 报告 (a) 目标 (b) 错误 (c) 需要的资源
4. **主动结束 turn**:要求 agent 结束 turn 而不是继续循环

**参考建议**:
- 在 OMA 的 `GAIA_SYSTEM_PROMPT` 中添加类似的 loop-stop 指导
- 考虑在 harness 层面增加硬性限制(如 `MAX_TOOL_CALLS = 30`)
- 在 runner 层面检测重复工具调用模式并主动中断

**相关文件**:
- `open-managed-agents/apps/agent/src/harness/platform-guidance.ts:14-15`
- `open-managed-agents/apps/agent/src/harness/platform-guidance.ts:25-26` (platformGuidance 组合)
- `open-managed-agents/apps/agent/src/harness/platform-guidance.ts:47-58` (composeSystemPrompt)

---

### 🟡 P1-b:多跳查询能力不足

**GAIA 测试现象**:
- Q6(学术作者链):论文 → 作者列表 → 第一论文
- Q42(娱乐多跳):TV 节目 → 餐厅 → 书籍
- Agent 在第一次搜索后找不到下一步线索

**open-managed-agents 实现**:

⚠️ **部分实现** - 工具能力具备,但缺乏策略指导

**已实现部分**:

1. **web_search 工具**(`apps/agent/src/harness/tools.ts:991-1039`):
   - 支持 DuckDuckGo(默认,免费)
   - 支持 Tavily API(需配置 `TAVILY_API_KEY`)
   - 支持 Anthropic 内置 web_search(Claude only)

2. **web_fetch 工具**(`apps/agent/src/harness/tools.ts:737-887`):
   - HTML/PDF/DOCX → Markdown 转换
   - 支持辅助模型摘要(可选)
   - 自动处理大文件(>32KB 时 offload 到文件系统)

**缺失部分**:
- ❌ 缺乏"链式搜索"策略指导
- ❌ 缺乏"中间结果验证"机制
- ❌ 缺乏"实体提取 → 下一步搜索"的明确流程

**参考建议**:

在 `platform-guidance.ts` 中增加多跳查询指导:

```typescript
export const multiHopSearchGuidance =
  "For complex questions requiring multiple information sources:\n" +
  "1. Break the question into sub-queries (A → B → C)\n" +
  "2. After each search/fetch, extract key entities for the next step\n" +
  "3. Verify intermediate results before proceeding\n" +
  "4. If a step fails, try alternative search terms or sources\n" +
  "5. Keep track of what you've found and what's still missing";
```

**相关文件**:
- `open-managed-agents/apps/agent/src/harness/tools.ts:737-887` (web_fetch)
- `open-managed-agents/apps/agent/src/harness/tools.ts:991-1080` (web_search)

---

### 🟡 P1-c:答案提取不完整

**GAIA 测试现象**:
- Q20:找到 "Annie" 但漏掉 "Levin"(人名不完整)
- Q43:找到 "9" 但正确答案是 "519"(数值错误)
- Agent 在长文本中迷失,无法精确定答案

**open-managed-agents 实现**:

❌ **未实现** - 缺乏答案验证和提取机制

**现状分析**:
- open-managed-agents 依赖 agent 自行提取答案
- 没有强制的"答案验证"步骤
- 没有"答案完整性检查"机制

**参考建议**:

在 `platform-guidance.ts` 中增加答案提取指导:

```typescript
export const answerExtractionGuidance =
  "When extracting answers from search results:\n" +
  "1. Names: Use full names (first + last), not just first names\n" +
  "2. Numbers: Double-check which column/field contains the answer\n" +
  "3. Dates: Include full date (YYYY-MM-DD) unless question specifies otherwise\n" +
  "4. Before answering, re-read the question to ensure completeness\n" +
  "5. If uncertain, provide the most specific answer found";
```

在 GAIA runner 中增加答案后处理:
- 人名标准化(检查是否包含姓和名)
- 数值验证(检查是否在合理范围内)
- 答案长度检查(过短可能不完整)

**相关文件**:
- 无对应实现,需新增

---

### 🟢 P2:冷门来源访问失败

**GAIA 测试现象**:
- Q18(Wikipedia 日志):web_fetch 返回难以解析的 Markdown
- Q42:长文本页面中关键信息定位困难

**open-managed-agents 实现**:

⚠️ **部分实现** - web_fetch 具备 Markdown 转换,但缺乏特殊网站优化

**已实现部分**:

1. **Markdown 转换器**(`apps/agent/src/harness/tools.ts:351`):
   - 支持 HTML/PDF/DOCX → Markdown
   - 可插拔的转换器接口(`toMarkdown`)

2. **辅助模型摘要**(`apps/agent/src/harness/tools.ts:382-384`):
   - 可选的辅助模型用于长文本摘要
   - 减轻主模型上下文压力

**缺失部分**:
- ❌ 缺乏针对 Wikipedia、GitHub 等特殊网站的优化解析器
- ❌ 缺乏"web_fetch 失败后自动降级到 web_search"机制
- ❌ 缺乏"结构化数据提取"(如表格、列表)的专门处理

**参考建议**:

1. **特殊网站优化**:
   ```typescript
   // Wikipedia 专用解析器
   if (url.includes("wikipedia.org")) {
     // 提取正文,过滤导航栏、参考文献
   }
   ```

2. **降级策略**:
   ```typescript
   // web_fetch 失败时,尝试 web_search 替代
   if (markdownExtractionFailed) {
     return `web_fetch failed for ${url}. Try: web_search("${pageTitle} site:${domain}")`;
   }
   ```

**相关文件**:
- `open-managed-agents/apps/agent/src/harness/tools.ts:737-887` (web_fetch)
- `open-managed-agents/apps/agent/src/harness/tools.ts:351` (Markdown 转换器接口)

---

## 三、优先级实施建议

### 立即实施(P0)

**任务**:修复 Session 终止失败

**步骤**:
1. 检查 `oma-platform/harness/oma_adapter/emit.py` 中的 `session.status_idle` 事件映射
2. 验证 SSE 流的 `broadcastEvent` 机制
3. 参考 `open-managed-agents/apps/agent/src/runtime/session-do.ts:1050-1056` 的实现

**预期效果**:测试时间从 10 分钟降到 2 分钟,效率提升 80%

---

### 短期实施(P1)

**任务 1**:添加工具循环检测

**步骤**:
1. 在 `GAIA_SYSTEM_PROMPT` 中添加 loop-stop 指导
2. 参考 `open-managed-agents/apps/agent/src/harness/platform-guidance.ts:14-15`
3. 在 runner 层面增加 `MAX_TOOL_CALLS` 硬性限制

**预期效果**:减少 30% 的无效工具调用

**任务 2**:增强多跳查询能力

**步骤**:
1. 在 `platform-guidance.ts` 中添加 multi-hop search 指导
2. 教 agent 在每次搜索后提取关键实体
3. 添加"中间结果验证"步骤

**预期效果**:通过率 +20% (Q6, Q42 等)

**任务 3**:优化答案提取

**步骤**:
1. 在 system prompt 中强调"完整答案"
2. 添加答案验证步骤(输出 ANSWER 前回查问题)
3. 对于数值答案,要求说明数据来源

**预期效果**:通过率 +15% (Q20, Q43 等)

---

### 中期实施(P2)

**任务**:优化冷门来源访问

**步骤**:
1. 针对 Wikipedia、GitHub 等网站优化 Markdown 转换
2. 添加 web_fetch 失败后的降级策略
3. 考虑添加专门的解析器

**预期效果**:通过率 +10%

---

## 四、总结

### 可复用实现

| 缺陷 | open-managed-agents 实现 | 复用难度 | 复用价值 |
|------|------------------------|---------|---------|
| P0 Session 终止 | ✅ 完整实现 | 低 | 高 |
| P1-a 工具循环 | ✅ 完整实现 | 低 | 高 |
| P1-b 多跳查询 | ⚠️ 工具具备,策略缺失 | 中 | 中 |
| P1-c 答案提取 | ❌ 未实现 | 高 | 中 |
| P2 冷门来源 | ⚠️ 基础实现,需优化 | 中 | 低 |

### 关键洞察

1. **Session 终止和工具循环是最容易修复的缺陷** - open-managed-agents 已有完整实现,只需参考移植
2. **多跳查询和答案提取需要策略层面的改进** - 不仅是工具能力,更需要 system prompt 的指导
3. **冷门来源访问是长尾问题** - 投入产出比低,可以后期优化

### 预期改进效果

- **修复 P0**:测试时间 -80%
- **修复 P0 + P1**:通过率 20% → 50%
- **修复全部**:通过率 20% → 70%

---

## 五、参考文件索引

### open-managed-agents 关键文件

1. **Session 状态管理**:
   - `apps/agent/src/runtime/session-do.ts:1050-1056` (status_idle 发射)
   - `apps/agent/src/runtime/session-do.ts:1834-1837` (interrupt 后的 idle)

2. **Platform Guidance**:
   - `apps/agent/src/harness/platform-guidance.ts:14-15` (loop-stop)
   - `apps/agent/src/harness/platform-guidance.ts:25-26` (platformGuidance)
   - `apps/agent/src/harness/platform-guidance.ts:47-58` (composeSystemPrompt)

3. **Web 工具**:
   - `apps/agent/src/harness/tools.ts:737-887` (web_fetch)
   - `apps/agent/src/harness/tools.ts:991-1080` (web_search)

### OMA 需要修改的文件

1. **Event 映射**:
   - `oma-platform/harness/oma_adapter/emit.py`

2. **System Prompt**:
   - `gaia/gaia_oma_runner.py:57-68` (GAIA_SYSTEM_PROMPT)

3. **Runner 逻辑**:
   - `gaia/gaia_oma_runner.py:181-236` (stream_events)
   - `gaia/gaia_oma_runner.py:274-287` (_looks_like_error)
