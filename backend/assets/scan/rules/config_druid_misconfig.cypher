MATCH
  (sinkNode:YmlKeyValue|PropertiesKeyValue)
WHERE
// 保留原始规则：两种命名格式的控制台启用配置（连字符式和驼峰式）
(sinkNode.name = 'spring.datasource.druid.stat-view-servlet.enabled' AND sinkNode.value = 'true') OR
(sinkNode.name = 'spring.datasource.druid.statViewServlet.enabled' AND sinkNode.value = 'true') OR

// 补充1：控制台登录验证缺失（两种命名格式均覆盖）
(sinkNode.name IN ['spring.datasource.druid.stat-view-servlet.login-username', 'spring.datasource.druid.statViewServlet.loginUsername'] AND
(sinkNode.value = '' OR sinkNode.value IS null)) OR  // 未配置用户名
(sinkNode.name IN ['spring.datasource.druid.stat-view-servlet.login-password', 'spring.datasource.druid.statViewServlet.loginPassword'] AND
(sinkNode.value = '' OR sinkNode.value IS null)) OR  // 未配置密码

// 补充2：允许所有IP访问控制台（两种命名格式）
(sinkNode.name IN ['spring.datasource.druid.stat-view-servlet.allow', 'spring.datasource.druid.statViewServlet.allow'] AND
sinkNode.value = '*') OR  // 全局允许

// 补充3：未限制危险IP（两种命名格式）
(sinkNode.name IN ['spring.datasource.druid.stat-view-servlet.deny', 'spring.datasource.druid.statViewServlet.deny'] AND
(sinkNode.value = '' OR sinkNode.value IS null)) OR  // 未配置禁止IP

// 补充4：SQL监控泄露敏感信息
(sinkNode.name IN ['spring.datasource.druid.filter.stat.enabled', 'spring.datasource.druid.filter.stat.enable'] AND
sinkNode.value = 'true') AND  // 启用SQL统计
(sinkNode.name IN ['spring.datasource.druid.filter.stat.log-slow-sql', 'spring.datasource.druid.filter.stat.logSlowSql'] AND
sinkNode.value = 'true') OR  // 记录慢查询（含完整SQL）

// 补充5：Web监控覆盖所有路径（泄露请求信息）
(sinkNode.name IN ['spring.datasource.druid.web-stat-filter.enabled', 'spring.datasource.druid.webStatFilter.enabled'] AND
sinkNode.value = 'true') AND  // 启用Web监控
(sinkNode.name IN ['spring.datasource.druid.web-stat-filter.url-pattern', 'spring.datasource.druid.webStatFilter.urlPattern'] AND
sinkNode.value = '/*')  // 监控所有URL

RETURN
  sinkNode AS path

/*
Chanzi-Separator

druid监控页面未授权访问

spring.datasource.druid.stat-view-servlet.enabled 是 Spring Boot 中 Druid 数据库连接池配置的一个属性，用于控制是否启用 Druid 的监控统计功能中的 StatViewServlet。这个属性的启用会带来一些安全风险，主要包括：

未授权访问风险：默认情况下，如果启用了 StatViewServlet，它可能会暴露敏感的监控信息，如数据库访问详情、慢查询记录等，而没有任何身份验证措施。这意味着任何人都可以访问这些监控页面，获取系统内部信息，可能导致数据泄露或被恶意利用。

信息泄露：监控页面可以展示数据库的实时状态、活跃连接数、查询执行时间等关键信息。未经授权的用户如果能够访问这些信息，可能会对系统的安全性和稳定性造成威胁。

系统稳定性风险：攻击者可以利用监控页面的信息来发起更有针对性的攻击，比如通过分析慢查询来找到可能的注入点，或者通过监控数据来推测系统的负载情况，从而发起拒绝服务攻击（DoS）。

Chanzi-Separator


为了降低这些风险，可以采取以下措施：

启用身份验证：在 Druid 的监控配置中设置用户名和密码，确保只有授权用户才能访问监控页面。可以通过在 application.yml 或 application.properties 文件中配置 spring.datasource.druid.stat-view-servlet.login-username 和 spring.datasource.druid.stat-view-servlet.login-password 来实现。

限制访问 IP：配置 IP 白名单（allow）和黑名单（deny），以控制哪些 IP 地址可以访问监控页面。例如，只允许特定的管理IP访问监控页面。

关闭重置功能：Druid 监控页面提供了一个“Reset All”功能，允许用户重置统计数据。这可能会被恶意用户利用来清除监控数据，隐藏攻击痕迹。可以通过设置 spring.datasource.druid.stat-view-servlet.reset-enable=false 来禁用此功能。

完全禁用监控页面：如果不使用 Druid 的监控功能，可以完全禁用 StatViewServlet，以避免任何潜在的安全风险。可以通过设置 spring.datasource.druid.stat-view-servlet.enabled=false 来实现。

通过这些措施，可以有效地提高系统的安全性，防止未授权访问和信息泄露。

Chanzi-Separator
*/