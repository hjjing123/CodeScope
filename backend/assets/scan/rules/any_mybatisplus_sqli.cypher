MATCH
  (sourceNode)
  WHERE
  (
  sourceNode:DubboServiceArg OR
  sourceNode:JsfXhtmlArg OR
  sourceNode:JaxwsArg OR
  sourceNode:StrutsActionArg OR
  sourceNode:ThriftHandlerArg OR
  sourceNode:NettyHandlerArg OR
  sourceNode:JfinalControllerArg OR
  sourceNode:JbootControllerArg OR
  sourceNode:SpringControllerArg OR
sourceNode:SolonControllerArg OR
  sourceNode:SpringInterceptorArg OR
  sourceNode:JspServiceArg OR
  sourceNode:WebServletArg OR
  sourceNode:WebXmlServletArg OR
  sourceNode:WebXmlFilterArg OR
  sourceNode:JaxrsArg OR
  sourceNode:HttpHandlerArg
  ) AND
  NOT sourceNode.type  IN ['Long', 'Integer', 'HttpServletResponse']

MATCH
  (sinkNode)
  WHERE
  // QueryWrapper的风险方法
  ('apply' IN sinkNode.selectors AND 'QueryWrapper' IN sinkNode.receiverTypes) OR
  ('last' IN sinkNode.selectors AND 'QueryWrapper' IN sinkNode.receiverTypes) OR
  ('orderBy' IN sinkNode.selectors AND 'QueryWrapper' IN sinkNode.receiverTypes) OR
  ('orderByAsc' IN sinkNode.selectors AND 'QueryWrapper' IN sinkNode.receiverTypes) OR
  ('orderByDesc' IN sinkNode.selectors AND 'QueryWrapper' IN sinkNode.receiverTypes) OR
  ('having' IN sinkNode.selectors AND 'QueryWrapper' IN sinkNode.receiverTypes) OR
  ('groupBy' IN sinkNode.selectors AND 'QueryWrapper' IN sinkNode.receiverTypes) OR
  ('inSql' IN sinkNode.selectors AND 'QueryWrapper' IN sinkNode.receiverTypes) OR
  ('or' IN sinkNode.selectors AND 'QueryWrapper' IN sinkNode.receiverTypes) OR
  ('and' IN sinkNode.selectors AND 'QueryWrapper' IN sinkNode.receiverTypes) OR
  ('where' IN sinkNode.selectors AND 'QueryWrapper' IN sinkNode.receiverTypes) OR

  // LambdaQueryWrapper的风险方法
  ('apply' IN sinkNode.selectors AND 'LambdaQueryWrapper' IN sinkNode.receiverTypes) OR
  ('last' IN sinkNode.selectors AND 'LambdaQueryWrapper' IN sinkNode.receiverTypes) OR
  ('orderBy' IN sinkNode.selectors AND 'LambdaQueryWrapper' IN sinkNode.receiverTypes) OR
  ('orderByAsc' IN sinkNode.selectors AND 'LambdaQueryWrapper' IN sinkNode.receiverTypes) OR
  ('orderByDesc' IN sinkNode.selectors AND 'LambdaQueryWrapper' IN sinkNode.receiverTypes) OR
  ('having' IN sinkNode.selectors AND 'LambdaQueryWrapper' IN sinkNode.receiverTypes) OR
  ('groupBy' IN sinkNode.selectors AND 'LambdaQueryWrapper' IN sinkNode.receiverTypes) OR
  ('inSql' IN sinkNode.selectors AND 'LambdaQueryWrapper' IN sinkNode.receiverTypes) OR
  ('or' IN sinkNode.selectors AND 'LambdaQueryWrapper' IN sinkNode.receiverTypes) OR
  ('and' IN sinkNode.selectors AND 'LambdaQueryWrapper' IN sinkNode.receiverTypes) OR
  ('where' IN sinkNode.selectors AND 'LambdaQueryWrapper' IN sinkNode.receiverTypes) OR

  // UpdateWrapper的风险方法
  ('apply' IN sinkNode.selectors AND 'UpdateWrapper' IN sinkNode.receiverTypes) OR
  ('last' IN sinkNode.selectors AND 'UpdateWrapper' IN sinkNode.receiverTypes) OR
  ('orderBy' IN sinkNode.selectors AND 'UpdateWrapper' IN sinkNode.receiverTypes) OR
  ('set' IN sinkNode.selectors AND 'UpdateWrapper' IN sinkNode.receiverTypes) OR
  ('where' IN sinkNode.selectors AND 'UpdateWrapper' IN sinkNode.receiverTypes) OR
  ('and' IN sinkNode.selectors AND 'UpdateWrapper' IN sinkNode.receiverTypes) OR
  ('or' IN sinkNode.selectors AND 'UpdateWrapper' IN sinkNode.receiverTypes) OR
  ('inSql' IN sinkNode.selectors AND 'UpdateWrapper' IN sinkNode.receiverTypes) OR

  // LambdaUpdateWrapper的风险方法
  ('apply' IN sinkNode.selectors AND 'LambdaUpdateWrapper' IN sinkNode.receiverTypes) OR
  ('last' IN sinkNode.selectors AND 'LambdaUpdateWrapper' IN sinkNode.receiverTypes) OR
  ('orderBy' IN sinkNode.selectors AND 'LambdaUpdateWrapper' IN sinkNode.receiverTypes) OR
  ('set' IN sinkNode.selectors AND 'LambdaUpdateWrapper' IN sinkNode.receiverTypes) OR
  ('where' IN sinkNode.selectors AND 'LambdaUpdateWrapper' IN sinkNode.receiverTypes) OR
  ('and' IN sinkNode.selectors AND 'LambdaUpdateWrapper' IN sinkNode.receiverTypes) OR
  ('or' IN sinkNode.selectors AND 'LambdaUpdateWrapper' IN sinkNode.receiverTypes) OR
  ('inSql' IN sinkNode.selectors AND 'LambdaUpdateWrapper' IN sinkNode.receiverTypes) OR

  // 旧版本EntityWrapper的风险方法
  ('addFilter' IN sinkNode.selectors AND 'EntityWrapper' IN sinkNode.receiverTypes) OR
  ('orderBy' IN sinkNode.selectors AND 'EntityWrapper' IN sinkNode.receiverTypes) OR
  ('having' IN sinkNode.selectors AND 'EntityWrapper' IN sinkNode.receiverTypes)

MATCH
  p = shortestPath((sourceNode)-[*..30]->(sinkNode))
  WHERE none(n IN nodes(p) WHERE n.type IS NOT NULL AND n.type IN ['Long', 'Integer'])
RETURN
  p AS path


/*
Chanzi-Separator

MyBatis-Plus SQL注入

MyBatis-Plus 在绝大多数场景下使用 `#{}` 占位符，天然免疫 SQL 注入。

但以下6类典型场景仍可能触发注入，务必在日常开发与安全审计中重点排查：

 1. 使用 `${}` 直接拼接用户输入

| 场景 | 风险示例 | 修复 |
|---|---|---|
| 动态列名、表名、排序字段 | `${column}` / `${order}` | 改为 **白名单校验** + `#{}` |

2. 手动字符串拼接（非 Wrapper）

| 场景 | 风险示例 | 修复 |
|---|---|---|
| XML/注解里手写 SQL | `LIKE '%${name}%'` | `CONCAT('%', #{name}, '%')` |

3. `apply`/`last` 方法滥用

| 场景 | 风险示例 | 修复 |
|---|---|---|
| 追加额外 SQL 片段 | `.apply("name LIKE '%" + name + "%'")` | `.apply("name LIKE {0}", "%" + name + "%")` |
| 追加任意片段 | `.last("LIMIT " + limit)` | 写死或使用分页 API |

4. Wrapper 的 字段名 来自用户输入

| 场景 | 风险示例 | 修复 |
|---|---|---|
| 动态列名 | `.eq(column, value)` 中 `column` 可控 | 白名单校验或使用 `LambdaWrapper` |

5. 历史漏洞（已修复，需升级）

| CVE 编号 | 影响版本 | 细节 | 修复 |
|---|---|---|---|
| CVE-2022-25517 | ≤3.4.3 | 排序字段未过滤导致注入 | 升级 ≥3.5.0 |
| CVE-2024-35548 | ≤3.5.6 | UpdateWrapper 字段名未过滤 | 升级 ≥3.5.7 |
| CVE-2023-25330 | ≤3.5.3.1 | TenantPlugin 租户 ID 未过滤 | 升级 ≥3.5.4 |

6. 自定义 SQL 注入器（ISqlInjector）

| 场景 | 风险示例 | 修复 |
|---|---|---|
| 自定义通用方法 | 手写 SQL 拼接用户输入 | 统一使用 `#{}` 或 `SqlInjectionUtils.check()` |

总结

只要出现“字符串拼接 SQL”或“用户可控字段名”，就有注入风险。

升级最新版 + 白名单校验 + 禁用 `${}` + 合理使用 Wrapper，即可彻底堵住 MyBatis-Plus 的 SQL 注入漏洞。

Chanzi-Separator

MyBatis-Plus SQL 注入的修复方案

| 风险点 | 产生原因 | 修复措施（含示例） | 参考 |
|---|---|---|---|
| 1. 使用 `${}` 拼接** | 直接字符串拼接 | 一律改为 `#{}` 或使用 `CONCAT('%',#{name},'%')` 模糊查询  |  |
| 2. 排序/列名来自前端** | 字段名无法预编译 | 白名单校验：只允许 `id`、`name` 等固定值 |  |
| 3. `apply` 方法滥用** | 直接拼接 SQL 片段 | 使用占位符 `{0}`：`apply("date = {0}", value)` |  |
| 4. `last` 方法滥用** | 追加任意 SQL | 禁止拼接用户输入，写死或分页 API |  |
| 5. Wrapper 字段名可控** | 动态列名 | 使用 LambdaWrapper 或白名单 |  |
| 6. 历史版本漏洞** | ≤3.4.3 排序注入 | 升级到 ≥3.5.7 |  |
| 7. JSON 查询注入** | JSON 字段动态键 | 使用 `apply("JSON_EXTRACT(...{0})", key)` 占位符 |  |
| 8. 手动 SQL 拼接** | 手写 SQL 未转义 | 统一使用 MyBatis `<if>` + `#{}` |  |

修复示例

危险写法（存在注入）

```java
// 模糊查询
wrapper.like("name", "%" + name + "%"); // 其实这句 MyBatis-Plus 已自动转义，安全
// 真正危险的是：
wrapper.apply("name LIKE '%" + name + "%'");
```

安全写法

```java
// 1. 模糊查询
wrapper.like("name", name); // 内部使用 #{}

// 2. apply 安全拼接
wrapper.apply("DATE_FORMAT(create_time,'%Y-%m-%d') = {0}", dateStr);

// 3. 排序白名单
Set<String> allow = Set.of("id", "name", "create_time");
if (!allow.contains(orderField)) {
    throw new IllegalArgumentException("非法排序字段");
}
wrapper.orderByAsc(orderField);
```

总结

升级依赖 + 禁用 `${}` + 白名单校验 + 占位符绑定，可彻底堵住 MyBatis-Plus 的 SQL 注入风险 。

Chanzi-Separator
*/